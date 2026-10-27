"""A finite worker whose heartbeat can be paused and repaired by file controls."""
import json
from pathlib import Path
import time


run = Path.cwd()
deadline = time.monotonic() + 60
while not (run / "finish").exists() and time.monotonic() < deadline:
    if not (run / "pause-heartbeat").exists():
        (run / "heartbeat.txt").touch()
    time.sleep(.1)
result = {"completed": (run / "finish").exists(), "at": time.time()}
(run / "result.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
raise SystemExit(0 if result["completed"] else 1)
