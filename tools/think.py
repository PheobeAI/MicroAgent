# tools/think.py
from tools.base import MicroTool
from ui.console import console


class ThinkTool(MicroTool):
    name = "think"
    description = "在需要推理或规划时调用此工具，将思考内容记录为 thought 参数。此工具不产生外部效果，仅用于结构化推理。"
    inputs = {
        "thought": {
            "type": "string",
            "description": "当前的推理步骤、分析或计划",
        }
    }
    output_type = "string"

    def __init__(self, show_thinking: bool = True) -> None:
        super().__init__()
        self._show_thinking = show_thinking

    def forward(self, thought: str) -> str:
        if self._show_thinking:
            console.print(f"[dim]💭 {thought}[/dim]")
        return ""
