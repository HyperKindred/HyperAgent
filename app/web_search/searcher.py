"""Web search and content fetching using DuckDuckGo."""

import re
import html
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
SEARCH_URL = "https://html.duckduckgo.com/html/"
TIMEOUT = 15


def _strip_tags(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def search_web(
    query: str,
    max_results: int = 5,
    fetch_content: bool = True,
    max_content_chars: int = 2000,
) -> str:
    """Search the web via DuckDuckGo and return formatted results.

    Args:
        query: Search query.
        max_results: Number of results to return (1-8).
        fetch_content: Whether to fetch and summarise the top result.
        max_content_chars: Max characters to keep from fetched content.

    Returns:
        Formatted search results string.
    """
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        resp = session.post(
            SEARCH_URL,
            data={"q": query},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        html_text = resp.text
    except requests.RequestException as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return f"搜索失败：{e}"

    # Parse results using regex
    # DDG HTML: <a class="result__a" href="URL">TITLE</a>
    #           <a class="result__snippet">SNIPPET</a>
    #           <span class="result__url">DISPLAY_URL</span>
    titles = re.findall(
        r'<a\s+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        html_text,
        re.DOTALL,
    )
    snippets = re.findall(
        r'<a\s+class="result__snippet"[^>]*>(.*?)</a>',
        html_text,
        re.DOTALL,
    )

    if not titles:
        return "没有找到相关结果。"

    results = []
    for i, (url, title) in enumerate(titles[:max_results]):
        title_clean = _strip_tags(title)
        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        results.append({
            "title": title_clean,
            "url": html.unescape(url),
            "snippet": snippet,
        })

    # Fetch content from top result
    top_content = ""
    if fetch_content and results:
        try:
            r = session.get(results[0]["url"], timeout=TIMEOUT)
            if r.status_code == 200:
                text = _strip_tags(r.text)
                # Get meaningful text (skip boilerplate)
                text = re.sub(
                    r"(var |function |window\.|nav|menu|footer|sidebar)",
                    "",
                    text[:max_content_chars * 2],
                )
                if len(text) > max_content_chars:
                    text = text[:max_content_chars] + "..."
                top_content = text
        except requests.RequestException as e:
            logger.warning("Content fetch failed for %s: %s", results[0]["url"], e)

    # Format output
    lines = [f"**搜索结果：「{query}」**\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"  {i}. **{r['title']}**")
        lines.append(f"     {r['snippet']}")
        lines.append(f"     🔗 {r['url']}")

    if top_content:
        lines.append(f"\n📄 **{results[0]['title']} 内容摘要：**")
        lines.append(top_content[:max_content_chars])

    return "\n".join(lines)
