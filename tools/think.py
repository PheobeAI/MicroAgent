# tools/think.py
import sys
from tools.base import MicroTool


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
            # Write directly to the original terminal stdout (sys.__stdout__),
            # bypassing Rich's Live/status machinery which may buffer or suppress
            # console.print() calls while the spinner is active.
            out = getattr(sys, "__stdout__", None)
            if out is not None:
                out.write(f"\033[2m💭 {thought}\033[0m\n")
                out.flush()
        return ""
