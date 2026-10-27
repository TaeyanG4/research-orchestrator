"""Leave a visible artifact only if the worker actually starts."""

from pathlib import Path
import sys

Path(sys.argv[1]).write_text("worker completed\n", encoding="utf-8")
