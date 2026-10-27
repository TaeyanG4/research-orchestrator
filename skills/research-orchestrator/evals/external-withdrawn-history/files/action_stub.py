"""Local fixture: append observable delivery evidence without network access."""
import os
from pathlib import Path

with Path("attempts.log").open("a", encoding="utf-8") as stream:
    stream.write(os.environ.get("RO_IDEMPOTENCY_KEY", "missing") + "\n")
print("accepted local fixture delivery")
