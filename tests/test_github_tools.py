"""Tests for GitHub tools (mocked API calls)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agent.tools import (
    github_create_issue_tool,
    github_get_issue_tool,
    github_list_issues_tool,
    github_list_notifications_tool,
    github_search_issues_tool,
)


@pytest.fixture(autouse=True)
def setup_github_config():
    """Set fake GitHub token so config validation passes."""
    import app.config
    app.config.settings.github_token = "fake_github_token"


# ── get_notifications ─────────────────────────────────────────────────


class TestGitHubNotifications:
    def test_no_notifications(self):
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = []
            mock_get.return_value = mock_resp

            result = github_list_notifications_tool.invoke({})
            assert "没有未读" in result

    def test_has_notifications(self):
        fake_response = [
            {
                "id": "1",
                "reason": "review_requested",
                "subject": {
                    "title": "Update README",
                    "type": "PullRequest",
                    "url": "https://api.github.com/repos/owner/repo/pulls/42",
                },
                "repository": {"full_name": "owner/repo"},
            }
        ]
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_response
            mock_get.return_value = mock_resp

            result = github_list_notifications_tool.invoke({})
            assert "Update README" in result
            assert "owner/repo" in result
            assert "PullRequest" in result

    def test_missing_token(self):
        """Should raise ConnectionError when token is empty."""
        import app.config
        app.config.settings.github_token = ""

        import app.github.client
        with pytest.raises(ConnectionError):
            app.github.client.get_notifications()

    def test_network_failure_has_actionable_message(self):
        import app.github.client

        with patch(
            "app.github.client.requests.get",
            side_effect=requests.ConnectionError("connection refused"),
        ):
            with pytest.raises(ConnectionError, match="无法连接 GitHub"):
                app.github.client.get_notifications()


# ── search_issues ──────────────────────────────────────────────────────


class TestGitHubSearchIssues:
    def test_search_no_results(self):
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"total_count": 0, "items": []}
            mock_get.return_value = mock_resp

            result = github_search_issues_tool.invoke({"query": "nonexistent"})
            assert "没有找到" in result

    def test_search_with_results(self):
        fake_response = {
            "total_count": 2,
            "items": [
                {
                    "number": 1,
                    "title": "Fix login bug",
                    "state": "open",
                    "user": {"login": "user1"},
                    "comments": 3,
                    "created_at": "2026-06-01T00:00:00Z",
                    "labels": [{"name": "bug"}],
                },
                {
                    "number": 2,
                    "title": "Add tests",
                    "state": "closed",
                    "user": {"login": "user2"},
                    "comments": 0,
                    "created_at": "2026-06-02T00:00:00Z",
                    "labels": [],
                    "pull_request": {"url": "..."},
                },
            ],
        }
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_response
            mock_get.return_value = mock_resp

            result = github_search_issues_tool.invoke({"query": "bug"})
            assert "Fix login bug" in result
            assert "Add tests" in result
            assert "找到 2 个结果" in result


# ── create_issue ──────────────────────────────────────────────────────


class TestGitHubCreateIssue:
    def test_create_issue(self):
        with patch("app.github.client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {
                "number": 42,
                "title": "Test bug",
                "html_url": "https://github.com/owner/repo/issues/42",
            }
            mock_post.return_value = mock_resp

            result = github_create_issue_tool.invoke({
                "repo": "owner/repo",
                "title": "Test bug",
                "body": "Found a bug when...",
            })
            assert "已创建" in result
            assert "42" in result
            assert "owner/repo" in result or "github.com" in result


# ── get_issue ─────────────────────────────────────────────────────────


class TestGitHubGetIssue:
    @patch("app.github.client.requests.get")
    def test_get_issue(self, mock_get):
        # First call: get issue
        mock_issue_resp = MagicMock()
        mock_issue_resp.status_code = 200
        mock_issue_resp.json.return_value = {
            "number": 42,
            "title": "Test Issue",
            "state": "open",
            "user": {"login": "author"},
            "created_at": "2026-06-10T00:00:00Z",
            "updated_at": "2026-06-11T00:00:00Z",
            "body": "This is the issue description.",
            "comments": 2,
            "labels": [{"name": "enhancement"}],
        }
        mock_get.return_value = mock_issue_resp

        result = github_get_issue_tool.invoke({
            "repo": "owner/repo",
            "issue_number": 42,
        })
        assert "Test Issue" in result
        assert "42" in result
        assert "enhancement" in result
        assert "author" in result


# ── list_issues ──────────────────────────────────────────────────────


class TestGitHubListIssues:
    def test_list_open_issues(self):
        fake_issues = [
            {
                "number": 1,
                "title": "Bug fix",
                "state": "open",
                "user": {"login": "user1"},
                "comments": 2,
            },
            {
                "number": 2,
                "title": "New feature",
                "state": "open",
                "user": {"login": "user2"},
                "comments": 0,
            },
        ]
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_issues
            mock_get.return_value = mock_resp

            result = github_list_issues_tool.invoke({
                "repo": "owner/repo",
            })
            assert "Bug fix" in result
            assert "New feature" in result
            assert "owner/repo" in result

    def test_list_no_issues(self):
        with patch("app.github.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = []
            mock_get.return_value = mock_resp

            result = github_list_issues_tool.invoke({
                "repo": "owner/repo",
            })
            assert "没有" in result
