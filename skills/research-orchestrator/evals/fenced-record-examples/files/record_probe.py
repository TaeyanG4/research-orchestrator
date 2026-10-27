"""Replay real record hooks on fenced examples and live positive controls."""

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

scripts = Path(sys.argv[1]).resolve()
source = Path("agents.md").read_text(encoding="utf-8")
environment = {key: value for key, value in os.environ.items()
               if key not in {"RO_SLOT", "RO_SESSION", "CODEX_THREAD_ID"}}
future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
results = {}


def run(root, script, arguments, payload=None):
    argv = [sys.executable, str(scripts / script), *arguments]
    stdin = json.dumps(payload) if payload is not None else None
    completed = subprocess.run(argv, input=stdin, cwd=root, env=environment,
                               text=True, encoding="utf-8", capture_output=True, timeout=20)
    return {"argv": argv, "stdin": stdin, "exit_code": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr}


for name, opening, closing, inner in (
    ("tilde", "~~~markdown", "~~~", "```"),
    ("long-backtick", "````markdown", "````", "```"),
    ("long-tilde", "~~~~~", "~~~~~~", "~~~"),
):
    with tempfile.TemporaryDirectory(prefix="record-probe-") as directory:
        root = Path(directory)
        (root / "agents.md").write_text(source, encoding="utf-8", newline="\n")
        records = root / "discoveries.md"
        sample = f"## D-A-001 example\n- Date: {future}\n"
        fenced = f"{opening}\n{sample}{inner}\n{sample}{closing}\n"
        records.write_text(fenced, encoding="utf-8", newline="\n")
        allocated = run(root, "ro.py", ["--project", str(root), "next-id", "D"])
        # Retain an unchanged-file cache written by the old backtick parser.
        stamp = records.stat()
        legacy = {"discoveries.md": {"stamp": [stamp.st_mtime_ns, stamp.st_size],
                  "ids": ["D-A-001", "D-A-001"], "duplicate": ["D-A-001"],
                  "future": [future], "future_records": [["D-A-001", future]]}}
        (root / ".ro" / "records-hook.json").write_text(json.dumps(legacy), encoding="utf-8")
        payload = {"cwd": str(root), "tool_name": "Write", "tool_input": {"file_path": str(records)}}
        example = run(root, "ro_hook_runner.py", ["PostToolUse"], payload)
        snapshot = json.loads((root / ".ro" / "records-hook.json").read_text(encoding="utf-8"))
        reserved = json.loads((root / ".ro" / "ids.json").read_text(encoding="utf-8"))
        records.write_text(fenced + sample.replace("example", "live") * 2, encoding="utf-8", newline="\n")
        live = run(root, "ro_hook_runner.py", ["PostToolUse"], payload)
        results[name] = {"allocated": allocated, "example": example,
                         "example_snapshot": snapshot["discoveries.md"],
                         "example_reservations": sorted(reserved), "live": live}

Path("hook-records.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, sort_keys=True))
