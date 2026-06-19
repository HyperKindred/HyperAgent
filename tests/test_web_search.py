"""Tests for Web search HTML parsers.

Tests use mock HTML pages that mimic DuckDuckGo and Bing result pages,
so these tests are fast, deterministic, and don't require network access.
"""

from __future__ import annotations

import pytest
import requests
from unittest.mock import patch

# The parser functions to test
from app.web_search.searcher import (
    _parse_duckduckgo,
    _parse_bing,
    _fetch_url_content,
    search_web,
    BACKENDS,
)


# ── DuckDuckGo parser ─────────────────────────────────────────────────────

DUCKDUCKGO_HTML = """
<html><body>
<div class="results">
<div class="result">
  <a class="result__a" href="https://example.com/page1">Example Page One</a>
  <a class="result__snippet">This is the snippet for the first result.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/page2">Example Page Two</a>
  <a class="result__snippet">Snippet for the second result, with more details.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/page3">Example Page Three</a>
  <a class="result__snippet">Third result snippet here.</a>
</div>
</div></body></html>"""

DUCKDUCKGO_EMPTY = "<html><body><div class='results'></div></body></html>"

# DuckDuckGo fallback layout (when .result__a has a different structure)
DUCKDUCKGO_FALLBACK_HTML = """
<html><body>
<div class="results">
<div class="result">
  <div class="result__title"><a rel="nofollow" href="https://fallback.com/1">Fallback Title 1</a></div>
  <div class="result__snippet">Fallback snippet one.</div>
</div>
</div></body></html>"""


class TestParseDuckDuckGo:
    def test_parses_multiple_results(self):
        results = _parse_duckduckgo(DUCKDUCKGO_HTML)
        assert len(results) == 3
        assert results[0]["title"] == "Example Page One"
        assert results[0]["url"] == "https://example.com/page1"
        assert results[0]["snippet"] == "This is the snippet for the first result."

    def test_parses_title_and_snippet(self):
        results = _parse_duckduckgo(DUCKDUCKGO_HTML)
        assert results[1]["title"] == "Example Page Two"
        assert results[1]["url"] == "https://example.com/page2"
        assert "more details" in results[1]["snippet"]

    def test_empty_html_returns_empty_list(self):
        results = _parse_duckduckgo(DUCKDUCKGO_EMPTY)
        assert results == []

    def test_no_results_div_returns_empty(self):
        results = _parse_duckduckgo("<html></html>")
        assert results == []

    def test_handles_unicode(self):
        html = DUCKDUCKGO_HTML.replace("Example Page One", "中文页面")
        results = _parse_duckduckgo(html)
        assert "中文页面" in results[0]["title"]

    def test_strips_excess_whitespace(self):
        html = '''<html><body>
        <div class="results">
        <div class="result">
          <a class="result__a" href="https://x.com/y">  Spaced   Title  </a>
          <a class="result__snippet">  Snippet    with\nspaces  </a>
        </div>
        </div></body></html>'''
        results = _parse_duckduckgo(html)
        assert results[0]["title"] == "Spaced Title"
        assert results[0]["snippet"] == "Snippet with spaces"


# ── Bing parser ───────────────────────────────────────────────────────────

BING_HTML = """
<html><body>
<ul class="b_results">
<li class="b_algo">
  <h2><a href="https://bing.example.com/article1">Bing Article One</a></h2>
  <p>This is the Bing snippet for article one.</p>
</li>
<li class="b_algo">
  <h2><a href="https://bing.example.com/article2">Bing Article Two</a></h2>
  <p>Bing snippet two has <strong>formatted</strong> text here.</p>
</li>
</ul></body></html>"""

BING_EMPTY = "<html><body><ul class='b_results'></ul></body></html>"


class TestParseBing:
    def test_parses_multiple_results(self):
        results = _parse_bing(BING_HTML)
        assert len(results) == 2
        assert results[0]["title"] == "Bing Article One"
        assert results[0]["url"] == "https://bing.example.com/article1"

    def test_parses_snippet(self):
        results = _parse_bing(BING_HTML)
        assert "snippet for article one" in results[0]["snippet"]

    def test_strips_inner_tags(self):
        """Bing snippets can contain <strong>, <em> etc. — they should be stripped."""
        results = _parse_bing(BING_HTML)
        assert "formatted" in results[1]["snippet"]
        assert "<strong>" not in results[1]["snippet"]

    def test_empty_results_list(self):
        results = _parse_bing(BING_EMPTY)
        assert results == []

    def test_no_b_algo_returns_empty(self):
        results = _parse_bing("<html><body><p>no results</p></body></html>")
        assert results == []

    def test_missing_h2_link_skips_block(self):
        html = """<html><body>
        <ul class="b_results">
        <li class="b_algo"><div>no link here</div></li>
        </ul></body></html>"""
        results = _parse_bing(html)
        assert results == []


# ── Fetch URL content ─────────────────────────────────────────────────────

class TestFetchUrlContent:
    def test_fetches_and_extracts_text(self):
        """Happy path: fetch a page and get clean text back."""
        mock_html = (
            "<html><body>"
            "<script>var x = 1;</script>"
            "<h1>Hello World</h1>"
            "<p>Some   content.</p>"
            "</body></html>"
        )
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = mock_html
            text = _fetch_url_content("https://example.com", max_chars=2000)

        assert "Hello World" in text
        assert "Some content" in text
        assert "script" not in text.lower()

    def test_strips_script_and_style(self):
        """JavaScript and CSS content must be excluded."""
        mock_html = (
            "<html><head><style>.cls{color:red}</style></head>"
            "<body><script>alert('x')</script>"
            "<p>Visible text</p></body></html>"
        )
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = mock_html
            text = _fetch_url_content("https://example.com")

        assert "Visible text" in text
        assert "alert" not in text
        assert "color:red" not in text

    def test_respects_max_chars(self):
        mock_html = "<html><body><p>" + "x" * 500 + "</p></body></html>"
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = mock_html
            text = _fetch_url_content("https://example.com", max_chars=100)
        assert len(text) == 100

    def test_request_error_returns_empty(self):
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            text = _fetch_url_content("https://example.com")
        assert text == ""


# ── search_web integration ────────────────────────────────────────────────

class TestSearchWeb:
    """Integration tests with mocked HTTP backends."""

    def test_happy_path_uses_duckduckgo(self):
        """DuckDuckGo should be tried first."""
        with patch("requests.Session.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = DUCKDUCKGO_HTML
            result = search_web("test query", fetch_content=False)

        assert "Example Page One" in result
        assert "搜索结果" in result
        assert chr(0x1f50d) in result

    def test_falls_back_to_bing(self):
        """When DuckDuckGo fails, Bing should be tried."""
        with patch("requests.Session.post", side_effect=requests.RequestException("DDG down")):
            with patch("requests.Session.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.text = BING_HTML
                result = search_web("fallback test", fetch_content=False)

        assert "Bing Article One" in result

    def test_all_backends_fail(self):
        """When all backends fail, return an error message."""
        with patch("requests.Session.post", side_effect=requests.RequestException("DDG down")):
            with patch("requests.Session.get", side_effect=requests.RequestException("Bing down")):
                result = search_web("failed query", fetch_content=False)

        assert "均不可用" in result

    def test_empty_query_sends_anyway(self):
        """Empty queries should still be sent (backend handles sanitization)."""
        with patch("requests.Session.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = DUCKDUCKGO_HTML
            result = search_web("", fetch_content=False)

        assert "搜索结果" in result

    def test_fetches_url_content_when_available(self):
        """When fetch_content=True, the first result body should be included."""
        with patch("requests.Session.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = DUCKDUCKGO_HTML
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.text = "<html><body><p>Article body content here.</p></body></html>"
                result = search_web("test", fetch_content=True)

        assert "Article body content here" in result
