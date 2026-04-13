# tests/tools/test_web_search.py
from unittest.mock import MagicMock, patch
from tools.web_search import WebSearchTool


def test_uses_duckduckgo_when_no_key():
    tool = WebSearchTool(tavily_api_key="")
    mock_results = [
        {"title": "Result 1", "href": "https://example.com/1", "body": "Content 1"},
        {"title": "Result 2", "href": "https://example.com/2", "body": "Content 2"},
    ]
    with patch("tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.__enter__ = lambda s: s
        mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.return_value.text.return_value = mock_results
        result = tool(query="test query")

    assert "Result 1" in result
    assert "https://example.com/1" in result


def test_uses_tavily_when_key_provided():
    tool = WebSearchTool(tavily_api_key="fake-key")
    mock_response = {
        "results": [
            {"title": "Tavily Result", "url": "https://tavily.com/1", "content": "Tavily Content"},
        ]
    }
    with patch("tools.web_search.TavilyClient") as mock_cls:
        mock_cls.return_value.search.return_value = mock_response
        result = tool(query="test query")

    assert "Tavily Result" in result
    assert "https://tavily.com/1" in result


def test_empty_results_message():
    tool = WebSearchTool(tavily_api_key="")
    with patch("tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.__enter__ = lambda s: s
        mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.return_value.text.return_value = []
        result = tool(query="query with no results")

    assert "未找到" in result
