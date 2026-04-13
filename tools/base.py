# tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolParam:
    name: str
    type: str        # "str" | "int" | "float" | "bool"
    description: str
    required: bool = True


class Tool(ABC):
    """Base class for all MicroAgent tools.

    Subclasses must define class attributes:
        name: str
        description: str
        parameters: list[ToolParam]

    And implement __call__(**kwargs) -> str.
    """

    name: str
    description: str
    parameters: list

    @abstractmethod
    def __call__(self, **kwargs) -> str:
        """Execute the tool. Must return a string result.
        Catch exceptions internally and return error description as string.
        """
        ...

    def describe(self) -> str:
        """Generate prompt-injection description text."""
        params = ", ".join(
            f"{p.name}: {p.type}" + ("" if p.required else " (可选)")
            for p in self.parameters
        )
        return f"- {self.name}({params}): {self.description}"


# ---------------------------------------------------------------------------
# Backward-compat alias (will be removed after all tools are migrated)
# ---------------------------------------------------------------------------
MicroTool = Tool