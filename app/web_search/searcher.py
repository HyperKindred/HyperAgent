"""Web search and content fetching with multi-backend fallback.

Tries DuckDuckGo first, then Bing (cn.bing.com, accessible in China),
then falls back to the user-configured custom search engine URL.

Uses selectolax for structured HTML parsing (more robust than regex).
"""

from __future__ import annotations

import html
import logging
import re

import requests
from selectolax.parser import HTMLParser

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 15


def _strip_tags(text: str) -> str:
    """Strip leftover HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _node_text(node) -> str:
    """Return the visible text content of a selectolax node."""
    if node is None:
        return ""
    return _strip_tags(node.text(deep=True, separator=" "))


def _parse_duckduckgo(html_text: str) -> list[dict]:
    """Parse DuckDuckGo HTML search results using CSS selectors."""
    parser = HTMLParser(html_text)
    results = []

    for article in parser.css(".result"):
        # First try .result__a for the link, then fall back to .result__title a
        link_el = article.css_first(".result__a")
        if link_el is None:
            link_el = article.css_first(".result__title a")
        if link_el is None:
            continue

        url = link_el.attributes.get("href", "")
        title = _node_text(link_el)

        # Try multiple snippet selectors in order
        snippet_el = (
            article.css_first(".result__snippet")
            or article.css_first(".result__snippet a")
        )
        snippet = _node_text(snippet_el) if snippet_el else ""

        if title or snippet:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


def _parse_bing(html_text: str) -> list[dict]:
    """Parse Bing HTML search results using CSS selectors."""
    parser = HTMLParser(html_text)
    results = []

    for block in parser.css("li.b_algo"):
        link_el = block.css_first("h2 a")
        if link_el is None:
            continue

        url = link_el.attributes.get("href", "")
        title = _node_text(link_el)

        snippet_el = block.css_first("p")
        snippet = _node_text(snippet_el) if snippet_el else ""

        results.append({"title": title, "url": url, "snippet": snippet})

    return results


BACKENDS = [
    {"name": "DuckDuckGo", "fn": _parse_duckduckgo, "url": "https://html.duckduckgo.com/html/", "method": "POST"},
    {"name": "Bing", "fn": _parse_bing, "url": "https://cn.bing.com/search", "method": "GET"},
]


def _try_backend(query: str, backend: dict) -> list[dict] | None:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        if backend["method"] == "POST":
            resp = session.post(backend["url"], data={"q": query}, timeout=TIMEOUT)
        else:
            resp = session.get(backend["url"], params={"q": query, "count": "10"}, timeout=TIMEOUT)
        resp.raise_for_status()
        results = backend["fn"](resp.text)
        return results if results else None
    except requests.RequestException as e:
        logger.warning("%s search failed: %s", backend["name"], e)
        return None


def _try_custom(query: str, url: str | None) -> list[dict] | None:
    if not url:
        return None
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        resp = session.get(url, params={"q": query}, timeout=TIMEOUT)
        resp.raise_for_status()
        parser = HTMLParser(resp.text)
        results = []
        for link in parser.css("a[href^=http]"):
            href = link.attributes.get("href", "")
            text = _node_text(link)
            if text:
                results.append({"title": text, "url": href, "snippet": ""})
        return results[:8] if results else None
    except requests.RequestException as e:
        logger.warning("Custom search failed: %s", e)
        return None


def _fetch_url_content(url: str, max_chars: int = 2000) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        parser = HTMLParser(resp.text)
        # Remove script and style nodes before extracting text
        for tag in ("script", "style"):
            for node in parser.css(tag):
                node.decompose()
        text = parser.body.text(deep=True, separator=" ")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return ""


def search_web(
    query: str,
    max_results: int = 5,
    fetch_content: bool = True,
    max_content_chars: int = 2000,
) -> str:
    all_results = []
    errors = []

    for backend in BACKENDS:
        results = _try_backend(query, backend)
        if results:
            all_results = results[:max_results]
            logger.info("Search used backend: %s", backend["name"])
            break
        errors.append(backend["name"])

    if not all_results:
        custom_url = getattr(settings, "search_engine_url", "") or ""
        if custom_url:
            results = _try_custom(query, custom_url)
            if results:
                all_results = results[:max_results]
            else:
                errors.append("custom")

    if not all_results:
        msg = "均不可用" if len(errors) == 0 else "、".join(errors) + " 均不可用"
        fmsg = chr(0x1f50d) + " 搜索【{0}】时，{1}，请检查网络连接。".format(query, msg)
        return fmsg

    lines = [chr(0x1f50d) + " **【{0}】的搜索结果：**".format(query)]
    for i, r in enumerate(all_results, 1):
        title = r["title"][:100]
        snippet = r.get("snippet", "")[:150]
        url = r["url"]
        lines.append("  {0}. **{1}**".format(i, title))
        if snippet:
            lines.append("     " + chr(0x1f4dd) + " {0}".format(snippet))
        lines.append("     " + chr(0x1f517) + " {0}".format(url[:80]))

    if fetch_content and all_results:
        first_url = all_results[0].get("url", "")
        if first_url:
            content = _fetch_url_content(first_url, max_chars=max_content_chars)
            if content:
                lines.append("\n\n" + chr(0x1f4c4) + " **首个结果内容摘要：**\n{0}".format(content[:max_content_chars]))

    return "\n".join(lines)
