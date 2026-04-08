# tests/tools/test_registry.py
from unittest.mock import MagicMock, patch
from core.config import ToolsConfig, WebSearchConfig, FileManagerConfig, SystemInfoConfig
from tools.registry import ToolRegistry


def test_all_enabled_loads_three_groups():
    config = ToolsConfig()
    mock_tool = MagicMock()

    with (
        patch("tools.web_search.WebSearchTool", return_value=mock_tool),
        patch("tools.file_manager.create_file_manager_tools", return_value=[mock_tool, mock_tool]),
        patch("tools.system_info.SystemInfoTool", return_value=mock_tool),
    ):
        tools = ToolRegistry(config).load()

    assert len(tools) == 4  # 1 web + 2 file_manager + 1 system_info


def test_disabled_tools_are_excluded():
    config = ToolsConfig(
        web_search=WebSearchConfig(enabled=False),
        system_info=SystemInfoConfig(enabled=False),
    )
    mock_tool = MagicMock()

    with patch("tools.file_manager.create_file_manager_tools", return_value=[mock_tool]):
        tools = ToolRegistry(config).load()

    assert len(tools) == 1
