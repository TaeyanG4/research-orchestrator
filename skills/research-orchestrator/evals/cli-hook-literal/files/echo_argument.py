from pathlib import Path
import sys

Path("argument.txt").write_text(sys.argv[1] + "\n", encoding="utf-8")
