from unittest.mock import MagicMock, patch
from tools.system_info import SystemInfoTool


def test_system_info_returns_string():
    tool = SystemInfoTool()
    mock_battery = MagicMock()
    mock_battery.percent = 80.0
    mock_battery.power_plugged = True
    mock_mem = MagicMock()
    mock_mem.used = 4 * 1024 ** 3
    mock_mem.total = 16 * 1024 ** 3
    mock_mem.percent = 25.0

    with (
        patch("psutil.cpu_percent", return_value=15.0),
        patch("psutil.virtual_memory", return_value=mock_mem),
        patch("psutil.sensors_battery", return_value=mock_battery),
    ):
        result = tool.forward()

    assert "15.0%" in result
    assert "4.0GB" in result
    assert "16.0GB" in result
    assert "80%" in result
    assert "充电" in result


def test_system_info_no_battery():
    tool = SystemInfoTool()
    mock_mem = MagicMock()
    mock_mem.used = 2 * 1024 ** 3
    mock_mem.total = 16 * 1024 ** 3
    mock_mem.percent = 12.5

    with (
        patch("psutil.cpu_percent", return_value=5.0),
        patch("psutil.virtual_memory", return_value=mock_mem),
        patch("psutil.sensors_battery", return_value=None),
    ):
        result = tool.forward()

    assert "未检测到" in result
