"""Notion REST API client.

Uses Notion Internal Integration Token for authentication.
API v1: https://api.notion.com/v1
"""

import json
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

REQUEST_TIMEOUT = 15


def _headers() -> dict[str, str]:
    """Return headers with current token."""
    if not settings.notion_token:
        raise ConnectionError(
            "Notion 未配置。请在设置中心填写 Notion Integration Token。"
        )
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make a GET request to the Notion API."""
    try:
        resp = requests.get(
            f"{BASE_URL}{path}",
            headers=_headers(),
            params=params or {},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise _network_error(exc) from exc
    _check_response(resp)
    return resp.json()


def _post(path: str, data: dict) -> dict[str, Any]:
    """Make a POST request to the Notion API."""
    try:
        resp = requests.post(
            f"{BASE_URL}{path}",
            headers=_headers(),
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise _network_error(exc) from exc
    _check_response(resp)
    return resp.json()


def _patch(path: str, data: dict) -> dict[str, Any]:
    """Make a PATCH request to the Notion API."""
    try:
        resp = requests.patch(
            f"{BASE_URL}{path}",
            headers=_headers(),
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise _network_error(exc) from exc
    _check_response(resp)
    return resp.json()


def _network_error(exc: requests.RequestException) -> ConnectionError:
    logger.warning("Notion request failed: %s", exc)
    return ConnectionError("无法连接 Notion，请检查网络后重试。")


def _check_response(resp: requests.Response) -> None:
    """Check Notion API response for errors."""
    if resp.status_code == 401:
        raise ConnectionError("Notion Token 无效或已过期，请在设置中心更新 Notion Token。")
    if resp.status_code == 403:
        raise ConnectionError("Notion 集成没有权限访问该页面。请在 Notion 中共享页面给集成。")
    if resp.status_code == 404:
        raise ValueError("未找到指定的 Notion 页面或数据库。请检查 ID 是否正确。")
    if resp.status_code == 429:
        raise ConnectionError("Notion API 速率限制已耗尽，请稍后再试。")
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Notion API returned %s", resp.status_code)
        raise ConnectionError("Notion 请求失败，请稍后重试。") from exc


def _extract_page_title(page: dict) -> str:
    """Extract the title from a Notion page object."""
    try:
        properties = page.get("properties", {})
        # Try common title property names
        for key in ("title", "Name", "名称", "标题", "Page"):
            prop = properties.get(key, {})
            if prop.get("type") == "title":
                parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in parts)
        # Fallback: look for any property with type "title"
        for prop in properties.values():
            if prop.get("type") == "title":
                parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in parts)
    except Exception:
        pass
    return "(无标题)"


def search_pages(query: str, per_page: int = 10) -> str:
    """Search pages and databases by title.

    Args:
        query: Search keyword.
        per_page: Max results (default 10, max 100).

    Returns:
        Formatted search results string.
    """
    data = _post("/search", {"query": query, "page_size": per_page})

    results = data.get("results", [])
    if not results:
        return f"🔍 没有找到包含「{query}」的 Notion 页面。"

    lines = [f"🔍 找到 {len(results)} 个匹配的 Notion 页面："]
    for i, item in enumerate(results, 1):
        obj_type = item.get("object", "unknown")
        object_type = item.get("type", obj_type)  # "page" or "database"
        icon_emoji = "📄" if object_type == "page" else "🗄️"
        title = _extract_page_title(item)

        # Get page/database ID (last part of URL)
        item_id = item.get("id", "")
        short_id = item_id.replace("-", "")[:8] if item_id else ""

        lines.append(f"  {i}. {icon_emoji} **{title}**")
        lines.append(f"       ID: {short_id}... | 类型: {object_type}")

    return "\n".join(lines)


def get_page(page_id: str) -> str:
    """Get the title and properties of a page.

    Args:
        page_id: 32-char Notion page ID (with or without hyphens).

    Returns:
        Page metadata string.
    """
    # Normalize ID: remove hyphens if present
    clean_id = page_id.replace("-", "")
    if len(clean_id) != 32:
        # Maybe it's a short ID, try full UUID format
        clean_id = page_id

    data = _get(f"/pages/{clean_id}")
    title = _extract_page_title(data)
    url = data.get("url", "")
    created = data.get("created_time", "")[:10]
    updated = data.get("last_edited_time", "")[:10]

    lines = [
        f"📄 **{title}**",
        f"   🔗 {url}",
        f"   创建: {created} · 更新: {updated}",
    ]

    # Show properties
    properties = data.get("properties", {})
    prop_lines = []
    for key, prop in properties.items():
        ptype = prop.get("type", "")
        if ptype == "title":
            continue  # already shown as title
        value = _format_property_value(prop)
        if value:
            prop_lines.append(f"   {key}: {value}")

    if prop_lines:
        lines.append("   📋 **属性：**")
        lines.extend(prop_lines)

    return "\n".join(lines)


def _format_property_value(prop: dict) -> str:
    """Format a Notion property value as text."""
    ptype = prop.get("type", "")
    value = prop.get(ptype)

    if value is None:
        return ""

    if ptype == "rich_text":
        return "".join(t.get("plain_text", "") for t in value)
    elif ptype == "select":
        return value.get("name", "") if value else ""
    elif ptype == "multi_select":
        return ", ".join(item.get("name", "") for item in value)
    elif ptype == "date":
        if value:
            parts = [value.get("start", "")]
            if value.get("end"):
                parts.append(f"→ {value['end']}")
            return " ".join(parts)
        return ""
    elif ptype == "checkbox":
        return "✅" if value else "❌"
    elif ptype == "number":
        return str(value) if value is not None else ""
    elif ptype == "email":
        return value or ""
    elif ptype == "phone_number":
        return value or ""
    elif ptype == "url":
        return value or ""
    elif ptype == "status":
        return value.get("name", "") if value else ""
    elif ptype == "people":
        names = [p.get("name", "") for p in value if p.get("name")]
        return ", ".join(names) if names else ""
    else:
        return str(value)[:100] if value else ""


def get_page_content(page_id: str, max_chars: int = 5000) -> str:
    """Read the full content of a page (recursively fetching blocks).

    Args:
        page_id: 32-char Notion page ID.
        max_chars: Max content length to return (default 5000).

    Returns:
        Page content as plain text.
    """
    clean_id = page_id.replace("-", "")

    # Get page metadata first
    page_data = _get(f"/pages/{clean_id}")
    title = _extract_page_title(page_data)

    # Fetch blocks recursively
    blocks = _get_blocks_recursive(clean_id, max_chars)

    content = f"📄 **{title}**\n\n{blocks}"
    return content.strip()


def _get_blocks_recursive(block_id: str, max_chars: int = 5000, depth: int = 0) -> str:
    """Recursively fetch block children and convert to plain text."""
    if depth > 3:
        return ""

    data = _get(f"/blocks/{block_id}/children")
    results = data.get("results", [])

    lines = []
    char_count = 0

    for block in results:
        if char_count >= max_chars:
            lines.append("...(内容过长，已截断)")
            break

        block_type = block.get("type", "unsupported")
        block_data = block.get(block_type, {})

        # Extract rich text from the block
        text = ""
        if "rich_text" in block_data:
            text = "".join(t.get("plain_text", "") for t in block_data["rich_text"])

        # Format based on block type
        prefix = ""
        suffix = ""
        if block_type in ("heading_1",):
            prefix = "# "
            suffix = ""
        elif block_type in ("heading_2",):
            prefix = "## "
        elif block_type in ("heading_3",):
            prefix = "### "
        elif block_type in ("bulleted_list_item",):
            prefix = "• "
        elif block_type in ("numbered_list_item",):
            prefix = "  "
        elif block_type in ("to_do",):
            checked = block_data.get("checked", False)
            prefix = "✅ " if checked else "⬜ "
        elif block_type in ("quote",):
            prefix = "> "
        elif block_type in ("code",):
            lang = block_data.get("language", "")
            text = f"```{lang}\n{text}\n```"
        elif block_type in ("divider",):
            text = "---"
        elif block_type in ("callout",):
            icon = block_data.get("icon", {}).get("emoji", "💡")
            prefix = f"{icon} "
        elif block_type in ("image",):
            text = "[图片]"
        elif block_type in ("bookmark", "embed", "video"):
            url = block_data.get("url", "")
            text = f"[链接] {url}" if url else "[链接]"

        if text:
            line = f"{prefix}{text}"
            lines.append(line)
            char_count += len(line)

        # Recurse into child blocks
        if block.get("has_children"):
            child_content = _get_blocks_recursive(
                block["id"], max_chars - char_count, depth + 1
            )
            if child_content:
                lines.append(child_content)
                char_count += len(child_content)

    return "\n".join(lines)


def create_page(
    title: str,
    content: str = "",
    parent_page_id: str = "",
) -> str:
    """Create a new page under a parent page.

    Args:
        title: Page title.
        content: Optional page content (plain text, will be converted to paragraphs).
        parent_page_id: Parent page ID. If empty, creates in the workspace root
                       (must be shared with the integration).

    Returns:
        Confirmation string with page URL.
    """
    if not parent_page_id:
        # We need at least the first 8 chars of a page ID to attempt
        # Without it, search for a root page
        return "❌ 请先提供父页面 ID（parent_page_id），或先使用 notion_search_tool 找到目标页面。"

    clean_parent = parent_page_id.replace("-", "")

    # Build the children blocks from content
    children = []
    if content:
        for paragraph in content.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            # Check for headings
            if paragraph.startswith("### "):
                text = paragraph[4:]
                children.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    },
                })
            elif paragraph.startswith("## "):
                text = paragraph[3:]
                children.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    },
                })
            elif paragraph.startswith("# "):
                text = paragraph[2:]
                children.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    },
                })
            elif paragraph.startswith("- ") or paragraph.startswith("• "):
                for line in paragraph.split("\n"):
                    line = line.strip().lstrip("- •")
                    if line:
                        children.append({
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [{"type": "text", "text": {"content": line}}]
                            },
                        })
            else:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": paragraph}}]
                    },
                })

    # Build the request body
    body = {
        "parent": {"page_id": clean_parent},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
    }
    if children:
        body["children"] = children

    data = _post("/pages", body)
    page_url = data.get("url", "")
    page_id = data.get("id", "")

    return f"✅ 已创建 Notion 页面：**{title}**\n   🔗 {page_url or f'Page ID: {page_id}'}"


def query_database(
    database_id: str,
    filter_text: str = "",
    sorts: str = "",
    per_page: int = 10,
) -> str:
    """Query a Notion database.

    Args:
        database_id: 32-char database ID.
        filter_text: Optional filter value (searches across all text properties).
        sorts: Optional sort field (e.g. "created_time").
        per_page: Max results (default 10, max 100).

    Returns:
        Formatted database entries string.
    """
    clean_id = database_id.replace("-", "")

    body: dict[str, Any] = {"page_size": per_page}

    # Simple filter: search across all text properties
    if filter_text:
        body["filter"] = {
            "property": "title",
            "title": {"contains": filter_text},
        }

    # Sort
    if sorts:
        direction = "ascending" if sorts.startswith("-") else "descending"
        field = sorts.lstrip("-")
        body["sorts"] = [{"property": field, "direction": direction}]

    data = _post(f"/databases/{clean_id}/query", body)

    # Get database title
    db_info = _get(f"/databases/{clean_id}")
    db_title = _extract_page_title(db_info)

    results = data.get("results", [])
    if not results:
        return f"📭 数据库「{db_title}」中没有匹配的条目。"

    lines = [f"🗄️ **{db_title}** — {len(results)} 条记录："]
    for i, item in enumerate(results, 1):
        # Get first text property as the title
        title = _extract_page_title(item)
        item_id = item.get("id", "")[:8]

        # Show properties
        props = []
        for key, prop in item.get("properties", {}).items():
            ptype = prop.get("type", "")
            if ptype == "title":
                continue
            val = _format_property_value(prop)
            if val:
                props.append(f"{key}: {val[:50]}")

        prop_str = " | ".join(props[:3])  # Limit to first 3 props
        lines.append(f"  {i}. **{title}** ({item_id})")
        if prop_str:
            lines.append(f"      {prop_str}")

    return "\n".join(lines)
