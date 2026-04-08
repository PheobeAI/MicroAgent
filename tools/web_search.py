# tools/web_search.py - stub for registry tests
from tools.base import MicroTool

class WebSearchTool(MicroTool):
    name = "web_search"
    description = "stub"
    inputs = {"query": {"type": "string", "description": "query"}}
    output_type = "string"
    def __init__(self, tavily_api_key: str = "") -> None:
        super().__init__()
    def forward(self, query: str) -> str:
        return ""
