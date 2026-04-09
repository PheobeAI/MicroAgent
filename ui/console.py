# ui/console.py
import sys
from rich.console import Console

# Pin file= to the real stdout at import time.  After ui.logger.setup() redirects
# sys.stdout to the log file, this console still writes to the terminal.
console = Console(file=sys.stdout)
