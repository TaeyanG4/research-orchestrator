"""Replay local scanner failures through the public pre-push hook response."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--scripts", required=True)
parser.add_argument("--project", required=True)
parser.add_argument("--normal", action="store_true")
args = parser.parse_args()
sys.path.insert(0, args.scripts)
import ro_evidence
import ro_hooks
from ro_proc import no_window_flags
from ro_state import Project

project = Project(Path(args.project), slot="A", session="public-gate-fixture")


def git(*values):
    return subprocess.check_output(["git", "-C", str(project.root), *values], text=True,
                                   creationflags=no_window_flags()).strip()


tip, base = git("rev-parse", "HEAD"), git("rev-parse", "HEAD~1")
refs = f"refs/heads/main {tip} refs/heads/main {base}\n"
count = len(git("rev-list", "--objects", tip, "--not", base, "--").splitlines())

if args.normal:
    report = ro_hooks.hook(project, "pre-push", {}, refs=refs)
    output = "normal-gate.json"
else:
    report = {"objects": count, "default_seconds": ro_evidence._scan_settings(project, count)[1]}
    original_cache, original_git = ro_evidence._cache, ro_evidence._git

    def timeout(*args, **kwargs):
        raise ValueError("publish scan deadline exceeded: synthetic-untrusted-exception-content")

    try:
        ro_evidence._cache = timeout
        report["after_enumeration"] = ro_hooks.hook(project, "pre-push", {}, refs=refs)
        ro_evidence._cache = original_cache
        ro_evidence._git = timeout
        report["before_enumeration"] = ro_hooks.hook(project, "pre-push", {}, refs=refs)
    finally:
        ro_evidence._cache, ro_evidence._git = original_cache, original_git
    output = "public-gate-report.json"
Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
