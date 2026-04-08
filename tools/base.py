# tools/base.py
from smolagents import Tool


class MicroTool(Tool):
    """Base class for all MicroAgent tools.
    Subclasses must define: name, description, inputs, output_type, forward().
    """
    pass
