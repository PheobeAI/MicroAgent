# tools/web_search.py
try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore

from tools.base import Tool, ToolParam


class WebSearchTool(Tool):
    name = "web_search"
    description = "搜索网络并返回相关结果摘要。提供搜索关键词或完整问题。"
    parameters = [ToolParam("query", "str", "搜索关键词或问题")]

    def __init__(self, tavily_api_key: str = "") -> None:
        self._use_tavily = bool(tavily_api_key)
        self._tavily_api_key = tavily_api_key

    def __call__(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if self._use_tavily:
            return self._search_tavily(query)
        return self._search_duckduckgo(query)

    def _search_tavily(self, query: str) -> str:
        try:
            client = TavilyClient(api_key=self._tavily_api_key)
            response = client.search(query, max_results=5)
            results = response.get("results", [])
            if not results:
                return "未找到相关结果"
            lines = [
                f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['content'][:200]}"
                for i, r in enumerate(results)
            ]
            return "\n\n".join(lines)
        except Exception as e:
            return f"错误：Tavily 搜索失败: {e}"

    def _search_duckduckgo(self, query: str) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return "未找到相关结果"
            lines = [
                f"{i + 1}. {r['title']}\n   {r['href']}\n   {r['body'][:200]}"
                for i, r in enumerate(results)
            ]
            return "\n\n".join(lines)
        except Exception as e:
            return f"错误：DuckDuckGo 搜索失败: {e}"