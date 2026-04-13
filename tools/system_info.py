import psutil

from tools.base import Tool, ToolParam


class SystemInfoTool(Tool):
    name = "system_info"
    description = "获取当前系统状态，包括CPU使用率、内存占用和电池状态。无需输入参数。"
    parameters: list = []

    def __call__(self, **kwargs) -> str:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        lines = [
            f"CPU使用率: {cpu}%",
            f"内存: {mem.used / (1024 ** 3):.1f}GB / {mem.total / (1024 ** 3):.1f}GB ({mem.percent}%)",
        ]

        if battery:
            status = "正在充电" if battery.power_plugged else "未充电"
            lines.append(f"电池: {battery.percent:.0f}%，{status}")
        else:
            lines.append("电池: 未检测到")

        return "\n".join(lines)