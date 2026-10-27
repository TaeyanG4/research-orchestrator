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


def reviewed_project(target, env):
    """An initialized project whose changed stage cites a reviewed two-file directory."""
    target.mkdir()
    sys.path.insert(0, str(SCRIPTS))
    from ro_proc import no_window_flags
    subprocess.run([sys.executable, str(SCRIPTS / "init_research_orchestrator.py"), str(target), "-n", "started",
                    "--preset", "solo-research", "--platforms", "Claude Code", "--user", "operator"],
                   check=True, capture_output=True, env=env, timeout=60, creationflags=no_window_flags())
    run = target / "run"
    run.mkdir()
    for index in range(2):
        (run / f"part-{index}.txt").write_text(f"reviewed result {index}\n", encoding="utf-8")
    handoff = target / "handoff.md"
    handoff.write_text(handoff.read_text(encoding="utf-8").rstrip("\n") + "\n\n"
                       "### 2026-10-25 10:00 — A — H-A-01/s1\n- Host: Claude Code\n- User: operator\n"
                       "- Action: ran the stage\n- Result: reviewed\n- Artifacts: run\n"
                       "- Discovery updates: none — stage progress, no experiment\n- Review verdict: none\n"
                       "- Resource: none\n- Other executor: none\n- New plan items: none — nothing follows\n"
                       "- Decision: changed\n- Review artifact: run\n", encoding="utf-8", newline="\n")
    sys.path.insert(0, str(SCRIPTS))
    import ro_evidence
    from ro_state import Project
    ro_evidence.receipt_add(Project(target, slot="A", session="timing-review"), "run", "independent-reviewer",
                            "PASS", "H-A-01/s1:after")
    return target


def started_cleanly(output):
    context = output.get("hookSpecificOutput", {}).get("additionalContext", "")
    return (output.get("hookSpecificOutput", {}).get("hookEventName") == "SessionStart"
            and "Research Orchestrator" in context and "event.stage.review" not in context)


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
        started = reviewed_project(base / "started", env)
        empty = lambda output: output == {}
        scenarios = {"unrelated": (unrelated, ["PreToolUse"], empty),
                     "stop-no-jobs": (project, ["Stop", "--general"], empty),
                     "edit-no-jobs": (project, ["PreToolUse", "--tool", "edit"], empty),
                     "post-unchanged": (project, ["PostToolUse", "--general"], empty),
                     "pre-shell": (project, ["PreToolUse"], empty),
                     # A full startup brief: the checker reruns and hashes the receipt's review directory.
                     "session-start-review": (started, ["SessionStart", "--general"], started_cleanly)}
        for wrapper, command in commands.items():
            for name, (cwd, extra, expected) in scenarios.items():
                payload = json.dumps({"cwd": str(cwd), "tool_name": "Bash", "hook_event_name": extra[0],
                                      "source": "startup", "session_id": "timing-session",
                                      "tool_input": {"command": "echo ready"}})
                def invoke():
                    proc = subprocess.run([*command, *extra], input=payload, text=True, capture_output=True,
                                          cwd=cwd, env=env, timeout=10, creationflags=no_window_flags())
                    if proc.returncode or proc.stderr or not expected(json.loads(proc.stdout)):
                        raise RuntimeError(f"Unexpected hook result for {wrapper}/{name}: {proc.stdout[:400]}")
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
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, measurement in results.items():
        print(f"{name}: p95 {measurement['p95_ms']:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
