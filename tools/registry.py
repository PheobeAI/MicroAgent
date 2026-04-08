# tools/registry.py
from typing import List

from smolagents import Tool

from core.config import ToolsConfig


class ToolRegistry:
    def __init__(self, config: ToolsConfig) -> None:
        self._config = config

    def load(self) -> List[Tool]:
        tools: List[Tool] = []

        if self._config.web_search.enabled:
            from tools.web_search import WebSearchTool
            tools.append(WebSearchTool(self._config.web_search.tavily_api_key))

        if self._config.file_manager.enabled:
            from tools.file_manager import create_file_manager_tools
            tools.extend(create_file_manager_tools(self._config.file_manager))

        if self._config.system_info.enabled:
            from tools.system_info import SystemInfoTool
            tools.append(SystemInfoTool())

        return tools
