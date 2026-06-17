"""GitHub REST API client.

Uses Personal Access Token for authentication.
API v3 (REST): https://api.github.com
"""

import json
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": "",
    "Accept": "application/vnd.github.v3+json",
}

REQUEST_TIMEOUT = 15


def _headers() -> dict[str, str]:
    """Return headers with current token."""
    if not settings.github_token:
        raise ConnectionError(
            "GitHub 未配置。请在 .env 中设置 GITHUB_TOKEN（Personal Access Token）。"
        )
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make a GET request to the GitHub API."""
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers=_headers(),
        params=params or {},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise ConnectionError("GitHub Token 无效或已过期，请在 .env 中更新 GITHUB_TOKEN。")
    if resp.status_code == 403:
        raise ConnectionError("GitHub API 速率限制已耗尽，请稍后再试。")
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: dict) -> dict[str, Any]:
    """Make a POST request to the GitHub API."""
    resp = requests.post(
        f"{BASE_URL}{path}",
        headers=_headers(),
        json=data,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise ConnectionError("GitHub Token 无效或已过期，请在 .env 中更新 GITHUB_TOKEN。")
    if resp.status_code == 403:
        raise ConnectionError("GitHub API 速率限制已耗尽，请稍后再试。")
    resp.raise_for_status()
    return resp.json()


def get_notifications() -> str:
    """List unread GitHub notifications.

    Returns:
        Formatted notification list string.
    """
    data = _get("/notifications", params={"per_page": 20})

    if not data:
        return "✅ 没有未读的 GitHub 通知。"

    lines = ["🔔 **GitHub 未读通知：**"]
    for i, n in enumerate(data, 1):
        reason = n.get("reason", "unknown")
        subject = n.get("subject", {})
        title = subject.get("title", "(无标题)")
        n_type = subject.get("type", "Unknown")
        repo_name = n.get("repository", {}).get("full_name", "unknown")
        url = subject.get("url", "")

        # Extract issue/PR number from URL
        number = ""
        if url:
            parts = url.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                number = f" #{parts[-1]}"

        lines.append(f"  {i}. [{n_type}{number}] **{title}**")
        lines.append(f"       仓库: {repo_name}  |  原因: {reason}")

    return "\n".join(lines)


def search_issues(
    query: str,
    repo: str = "",
    state: str = "open",
    per_page: int = 10,
) -> str:
    """Search issues and pull requests.

    Args:
        query: Search keywords.
        repo: Optional repo filter (e.g. "owner/repo").
        state: "open", "closed", or "all".
        per_page: Max results (default 10, max 100).

    Returns:
        Formatted search results string.
    """
    q = query
    if repo:
        q += f" repo:{repo}"
    q += f" state:{state}"

    data = _get("/search/issues", params={"q": q, "per_page": per_page, "sort": "updated"})

    total = data.get("total_count", 0)
    items = data.get("items", [])

    if total == 0:
        return f"🔍 没有找到匹配的 issue 或 PR。"

    repo_filter = f" (仓库: {repo})" if repo else ""
    lines = [f"🔍 找到 {total} 个结果{repo_filter}："]
    for i, item in enumerate(items, 1):
        number = item["number"]
        title = item["title"]
        state_icon = "🟢" if item["state"] == "open" else "🔴"
        is_pr = "pull_request" in item
        icon = "🔄" if is_pr else "🐛"
        user = item["user"]["login"]
        comments = item.get("comments", 0)
        created = item["created_at"][:10]
        labels = ", ".join(l["name"] for l in item.get("labels", []))

        label_str = f" [{labels}]" if labels else ""
        lines.append(
            f"  {i}. {state_icon}{icon} **#{number} {title}**{label_str}"
            f"\n        by {user} · {created} · 💬 {comments}"
        )

    return "\n".join(lines)


def create_issue(
    repo: str,
    title: str,
    body: str = "",
) -> str:
    """Create an issue in a repository.

    Args:
        repo: Repository name in "owner/repo" format.
        title: Issue title.
        body: Issue body/description.

    Returns:
        Confirmation string with issue URL.
    """
    data = _post(f"/repos/{repo}/issues", {"title": title, "body": body})
    number = data["number"]
    html_url = data["html_url"]
    return f"✅ 已创建 Issue **#{number}**: {title}\n   🔗 {html_url}"


def get_issue(repo: str, issue_number: int) -> str:
    """Get details of a specific issue or PR.

    Args:
        repo: Repository in "owner/repo" format.
        issue_number: Issue or PR number.

    Returns:
        Formatted issue details string.
    """
    data = _get(f"/repos/{repo}/issues/{issue_number}")

    title = data["title"]
    state = data["state"]
    state_icon = "🟢" if state == "open" else "🔴"
    user = data["user"]["login"]
    created = data["created_at"][:10]
    updated = data["updated_at"][:10]
    body = data.get("body", "") or "(没有描述)"
    comments = data.get("comments", 0)
    is_pr = "pull_request" in data

    icon = "🔄 PR" if is_pr else "🐛 Issue"
    labels = ", ".join(l["name"] for l in data.get("labels", []))

    lines = [
        f"{state_icon} **{icon} #{issue_number}: {title}**",
        f"   作者: {user} · 创建: {created} · 更新: {updated} · 💬 {comments}",
    ]
    if labels:
        lines.append(f"   标签: {labels}")

    # Add PR-specific info
    if is_pr:
        pr_data = _get(f"/repos/{repo}/pulls/{issue_number}")
        lines.append(f"   分支: {pr_data['head']['ref']} → {pr_data['base']['ref']}")
        lines.append(f"   🟢 可合并: {'是' if pr_data.get('mergeable') else '否'}")

    if body:
        body_preview = body[:2000]
        lines.append(f"\n   📝 **描述：**\n{body_preview}")

    return "\n".join(lines)


def list_repo_issues(
    repo: str,
    state: str = "open",
    per_page: int = 10,
) -> str:
    """List issues and PRs for a repository.

    Args:
        repo: Repository in "owner/repo" format.
        state: "open", "closed", or "all".
        per_page: Max results (default 10, max 100).

    Returns:
        Formatted issue list string.
    """
    data = _get(f"/repos/{repo}/issues", params={"state": state, "per_page": per_page, "sort": "updated"})

    if not data:
        return f"📭 仓库 {repo} 没有 {state} 状态的 issue。"

    state_label = "🟢 开放" if state == "open" else "🔴 已关闭" if state == "closed" else "全部"
    lines = [f"📋 **{repo}** {state_label}的 issue/PR（最近 {len(data)} 条）："]
    for i, item in enumerate(data, 1):
        number = item["number"]
        title = item["title"]
        is_pr = "pull_request" in item
        icon = "🔄" if is_pr else "🐛"
        user = item["user"]["login"]
        comments = item.get("comments", 0)
        lines.append(f"  {i}. {icon} **#{number} {title}** — by {user} 💬 {comments}")

    return "\n".join(lines)
