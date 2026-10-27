"""A launcher that exits before its finite, locally owned worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


run = Path.cwd()
if len(sys.argv) == 1:
    (run / "input.txt").write_text("original input\n", encoding="utf-8")
    worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker"])
    (run / "launcher.json").write_text(json.dumps({"launcher": os.getpid(), "worker": worker.pid}), encoding="utf-8")
    time.sleep(.3)
else:
    root = next(path for path in run.parents if (path / "agents.md").is_file())
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            entries = json.loads((root / ".ro" / "jobs.json").read_text(encoding="utf-8"))
            entry = entries[-1]
            sample = {"at": time.time(), "worker": os.getpid(), "status": entry.get("status"),
                      "ended": entry.get("ended"), "monitor": entry.get("monitor")}
            with (run / "worker-samples.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps(sample) + "\n")
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(.1)
