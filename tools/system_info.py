# tools/system_info.py - stub for registry tests
from tools.base import MicroTool

class SystemInfoTool(MicroTool):
    name = "system_info"
    description = "stub"
    inputs = {}
    output_type = "string"
    def forward(self) -> str:
        return ""
