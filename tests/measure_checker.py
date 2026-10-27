#!/usr/bin/env python3
"""Measure full checker runs on a synthetic event history; no files survive the run.

    python tests/measure_checker.py --events 10000 --runs 3

Use --baseline-ref HEAD to compare the committed checker with the working copy.
Both checkers use the same current initializer, settings and generated project.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "research-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_project
import init_research_orchestrator as init
from ro_proc import no_window_flags


def synthetic_project(root: Path, count: int) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        code = init.main([str(root), "-n", "synthetic", "--preset", "quick", "--platforms", "Shell",
                          "--user", "operator", "--git", "off", "--environment", "windows/powershell"])
    if code:
        raise RuntimeError("synthetic project initialization failed")
    events = []
    for number in range(count):
        events.append(f"### 2026-10-24 12:00 — A — H-A-{number + 1:05}\n"
                      "- Host: Shell\n- User: operator\n- Action: completed routine maintenance\n"
                      "- Result: complete\n- Artifacts: none\n- Discovery updates: none — routine work\n"
                      "- Review verdict: none\n- Resource: none\n- Other executor: none\n"
                      "- New plan items: none — nothing follows\n")
    path = root / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + "\n".join(events), encoding="utf-8")


def measure(checker_type, root: Path, runs: int) -> float:
    elapsed = []
    for _ in range(runs):
        checker = checker_type(root, now=dt.datetime(2026, 10, 25, 12))
        start = time.perf_counter()
        code = checker.run(quiet=True)
        elapsed.append(time.perf_counter() - start)
        if code or any(issue.severity == "WARN" for issue in checker.issues):
            raise RuntimeError("synthetic project is not clean: " + "; ".join(i.render() for i in checker.issues))
    return statistics.median(elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=10000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--baseline-ref")
    args = parser.parse_args()
    if args.events < 1 or args.runs < 1:
        parser.error("events and runs must be positive")
    with tempfile.TemporaryDirectory(prefix="ro-checker-measure-") as directory:
        root = Path(directory)
        synthetic_project(root, args.events)
        if args.baseline_ref:
            relative = (SCRIPTS / "check_project.py").relative_to(ROOT).as_posix()
            git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
            exists = subprocess.run(git + ["cat-file", "-e", f"{args.baseline_ref}:{relative}"],
                                    cwd=ROOT, capture_output=True, creationflags=no_window_flags())
            if exists.returncode:
                sys.path.insert(0, str(ROOT))
                from scripts.evals.baseline import SKILL_SUBTREE
                relative = SKILL_SUBTREE + "/scripts/check_project.py"
            source = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "show",
                                              f"{args.baseline_ref}:{relative}"], cwd=ROOT,
                                             creationflags=no_window_flags())
            baseline = types.ModuleType("checker_baseline")
            baseline.__file__ = str(SCRIPTS / "check_project.py")
            sys.modules[baseline.__name__] = baseline
            try:
                exec(compile(source, baseline.__file__, "exec"), baseline.__dict__)
                print(f"baseline ({args.events} events, median of {args.runs}): "
                      f"{measure(baseline.Checker, root, args.runs):.3f}s", flush=True)
            finally:
                del sys.modules[baseline.__name__]
        print(f"working ({args.events} events, median of {args.runs}): "
              f"{measure(check_project.Checker, root, args.runs):.3f}s")


if __name__ == "__main__":
    main()
