"""Tests for Notion tools (mocked API calls)."""

from unittest.mock import MagicMock, patch

import pytest

from app.agent.tools import (
    notion_create_page_tool,
    notion_query_database_tool,
    notion_read_page_tool,
    notion_search_tool,
)


@pytest.fixture(autouse=True)
def setup_notion_config():
    """Set fake Notion token so config validation passes."""
    import app.config
    app.config.settings.notion_token = "fake_notion_token"


# ── search_pages ──────────────────────────────────────────────────────


class TestNotionSearch:
    def test_search_no_results(self):
        with patch("app.notion.client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"results": []}
            mock_post.return_value = mock_resp

            result = notion_search_tool.invoke({"query": "nonexistent"})
            assert "没有找到" in result

    def test_search_with_results(self):
        fake_response = {
            "results": [
                {
                    "object": "page",
                    "type": "page",
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "项目计划"}],
                        }
                    },
                },
                {
                    "object": "database",
                    "type": "database",
                    "id": "d4c3b2a1-f6e5-0987-dcba-4321fedcba98",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "任务跟踪"}],
                        }
                    },
                },
            ]
        }
        with patch("app.notion.client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_response
            mock_post.return_value = mock_resp

            result = notion_search_tool.invoke({"query": "项目"})
            assert "项目计划" in result
            assert "任务跟踪" in result
            assert "页面" in result or "database" in result


# ── read_page ─────────────────────────────────────────────────────────


class TestNotionReadPage:
    @patch("app.notion.client.requests.get")
    def test_read_page(self, mock_get):
        # First call: get page metadata
        mock_page_resp = MagicMock()
        mock_page_resp.status_code = 200
        mock_page_resp.json.return_value = {
            "id": "abc123",
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "plain_text": "我的笔记"}],
                }
            },
            "url": "https://notion.so/abc123",
            "created_time": "2026-01-01T00:00:00.000Z",
            "last_edited_time": "2026-06-15T00:00:00.000Z",
        }

        # Second call: get blocks children
        mock_blocks_resp = MagicMock()
        mock_blocks_resp.status_code = 200
        mock_blocks_resp.json.return_value = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "plain_text": "这是正文内容。"}]
                    },
                    "has_children": False,
                },
                {
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "plain_text": "小节标题"}]
                    },
                    "has_children": False,
                },
                {
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "plain_text": "列表项一"}]
                    },
                    "has_children": False,
                },
            ]
        }

        mock_get.side_effect = [mock_page_resp, mock_blocks_resp]

        result = notion_read_page_tool.invoke({"page_id": "abc123"})
        assert "我的笔记" in result
        assert "这是正文内容" in result
        assert "小节标题" in result
        assert "列表项一" in result


# ── create_page ───────────────────────────────────────────────────────


class TestNotionCreatePage:
    def test_create_page_no_parent(self):
        result = notion_create_page_tool.invoke({
            "title": "新页面",
            "parent_page_id": "",
        })
        assert "父页面" in result or "parent" in result

    def test_create_page_success(self):
        with patch("app.notion.client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "id": "new-page-id-123",
                "url": "https://notion.so/new-page-id-123",
            }
            mock_post.return_value = mock_resp

            result = notion_create_page_tool.invoke({
                "title": "新页面",
                "content": "这是正文内容",
                "parent_page_id": "parent-id-123",
            })
            assert "已创建" in result
            assert "新页面" in result


# ── query_database ────────────────────────────────────────────────────


class TestNotionQueryDatabase:
    def test_query_empty(self):
        with patch("app.notion.client.requests.get") as mock_get:
            with patch("app.notion.client.requests.post") as mock_post:
                # Database info (GET)
                mock_db_resp = MagicMock()
                mock_db_resp.status_code = 200
                mock_db_resp.json.return_value = {
                    "id": "db-id-123",
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "我的数据库"}],
                        }
                    }
                }
                mock_get.return_value = mock_db_resp

                # Query result (POST)
                mock_query_resp = MagicMock()
                mock_query_resp.status_code = 200
                mock_query_resp.json.return_value = {"results": []}
                mock_post.return_value = mock_query_resp

                result = notion_query_database_tool.invoke({
                    "database_id": "db-id-123",
                })
                assert "没有" in result or "数据库" in result

    @patch("app.notion.client.requests.get")
    @patch("app.notion.client.requests.post")
    def test_query_with_results(self, mock_post, mock_get):
        # Database info (GET)
        mock_db_resp = MagicMock()
        mock_db_resp.status_code = 200
        mock_db_resp.json.return_value = {
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "plain_text": "任务列表"}],
                }
            }
        }
        mock_get.return_value = mock_db_resp

        # Query result (POST)
        mock_query_resp = MagicMock()
        mock_query_resp.status_code = 200
        mock_query_resp.json.return_value = {
            "results": [
                {
                    "id": "item-1",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "任务一"}],
                        },
                        "Status": {
                            "type": "status",
                            "status": {"name": "进行中"},
                        },
                    },
                },
                {
                    "id": "item-2",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "任务二"}],
                        },
                        "Status": {
                            "type": "status",
                            "status": {"name": "已完成"},
                        },
                    },
                },
            ]
        }
        mock_post.return_value = mock_query_resp

        result = notion_query_database_tool.invoke({
            "database_id": "db-id-123",
        })
        assert "任务一" in result
        assert "任务二" in result
        assert "进行中" in result
