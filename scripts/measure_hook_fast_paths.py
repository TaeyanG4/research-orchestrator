#!/usr/bin/env python3
"""Measure local wrapper calls using temporary projects, without invoking an agent host."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills/research-orchestrator/scripts"


def percentile(samples):
    return sorted(samples)[math.ceil(.95 * len(samples)) - 1]


def measure(call, *, batches=3, samples=20):
    for _ in range(2):
        call()
    measurements = []
    for _ in range(batches):
        values = []
        for _ in range(samples):
            start = time.perf_counter()
            call()
            values.append((time.perf_counter() - start) * 1000)
        measurements.append(values)
    p95s = [percentile(values) for values in measurements]
    return {"samples_ms": measurements, "batch_p95_ms": p95s,
            "p95_ms": sorted(p95s)[len(p95s) // 2], "output_correct": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    results = {}
    with tempfile.TemporaryDirectory(prefix="ro-hook-timing-") as temporary:
        base = Path(temporary)
        project = base / "project"
        unrelated = base / "unrelated"
        project.mkdir()
        unrelated.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("CLAUDE", "CODEX", "RO_", "GEMINI", "ANTIGRAVITY"))
               and key not in ("BASH_ENV", "ENV", "CDPATH", "PYTHONPYCACHEPREFIX")}
        env.update(RO_HOOK_PYTHON=sys.executable, HOME=str(base / "home"), USERPROFILE=str(base / "home"),
                   LOCALAPPDATA=str(base / "cache"), XDG_CACHE_HOME=str(base / "cache"))
        texts = {"agents.md": "# Rules\n\n## Project settings\n- Profile: work\n- Enforcement: warn\n"
                              "- Environment: " + ("windows" if os.name == "nt" else "linux") + "/bash\n",
                 "plan.md": "# Plan\n\n## Queue\n",
                 "discoveries.md": "# Discoveries\n" + "fact\n" * 280000,
                 "handoff.md": "# Handoff\n\n### Agent: A\n- Current host: local\n" + "event\n" * 83334}
        for name, content in texts.items():
            path = project / name
            path.write_text(content, encoding="utf-8")
            os.utime(path, (1700000000, 1700000000))
        sys.path.insert(0, str(SCRIPTS))
        import ro_hooks
        from ro_proc import no_window_flags
        from ro_state import Project
        owner = Project(project, slot="A", session="timing-session")
        ro_hooks._snapshot(owner)
        os.utime(owner.state / "records-hook.json", (1700000060, 1700000060))
        ro_hooks._wrapper_snapshot(owner)
        os.utime(owner.state / "records-hook.ready", (1700000300, 1700000300))
        commands = {}
        if shell := shutil.which("sh"):
            commands["sh"] = [shell, (ROOT / "hooks/ro-hook.sh").as_posix()]
        if os.name == "nt":
            commands["cmd"] = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(ROOT / "hooks/ro-hook.cmd")]
        scenarios = {"unrelated": (unrelated, ["PreToolUse"]), "stop-no-jobs": (project, ["Stop", "--general"]),
                     "edit-no-jobs": (project, ["PreToolUse", "--tool", "edit"]),
                     "post-unchanged": (project, ["PostToolUse", "--general"]),
                     "pre-shell": (project, ["PreToolUse"])}
        for wrapper, command in commands.items():
            for name, (cwd, extra) in scenarios.items():
                payload = json.dumps({"cwd": str(cwd), "tool_name": "Bash",
                                      "tool_input": {"command": "echo ready"}})
                def invoke():
                    proc = subprocess.run([*command, *extra], input=payload, text=True, capture_output=True,
                                          cwd=cwd, env=env, timeout=10, creationflags=no_window_flags())
                    if proc.returncode or proc.stderr or json.loads(proc.stdout) != {}:
                        raise RuntimeError(f"Unexpected hook result for {wrapper}/{name}")
                results[wrapper + "/" + name] = measure(invoke)
        import ro_records
        ro_records._checker_brief(owner)
        saved = owner.read_json("checker-brief.json", {})
        saved["at"] -= 120
        owner.write_json("checker-brief.json", saved)
        def compact_cache():
            summary = ro_records._checker_brief(owner, compact=True)
            if summary[0] != saved["counts"] or summary[1] != saved["code"]:
                raise RuntimeError("Unexpected compact summary")
        results["in-process/compact-checker-cache"] = measure(compact_cache)
    report = {"date": dt.date.today().isoformat(), "os": platform.system(), "python": platform.python_version(),
              "scope": "Local synthetic calls, not agent-host probes or behaviour evals",
              "method": "2 warmups, 3 batches of 20 calls; median nearest-rank batch p95; correct output required",
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, measurement in results.items():
        print(f"{name}: p95 {measurement['p95_ms']:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
