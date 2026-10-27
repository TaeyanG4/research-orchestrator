"""Inject a local clock advance after real outgoing-object enumeration."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--scripts", required=True)
parser.add_argument("--project", required=True)
args = parser.parse_args()
sys.path.insert(0, args.scripts)
import ro_evidence
from ro_state import Project
from ro_proc import no_window_flags

project = Project(Path(args.project), slot="A", session="fixture")

def git(*values):
    return subprocess.check_output(["git", "-C", str(project.root), *values], text=True,
                                   creationflags=no_window_flags()).strip()

tip, base = git("rev-parse", "HEAD"), git("rev-parse", "HEAD~1")
count = len(git("rev-list", "--objects", tip, "--not", base, "--").splitlines())
report = {"objects": count, "default_seconds": ro_evidence._scan_settings(project, count)[1]}
clock, match = ro_evidence.time.monotonic, ro_evidence.first_match
now = [100.0]

def advance(patterns, chunks):
    now[0] += 10000
    ro_evidence._remaining()

try:
    ro_evidence.time.monotonic = lambda: now[0]
    ro_evidence.first_match = advance
    refs = f"refs/heads/main {tip} refs/heads/main {base}\n"
    try:
        ro_evidence.scan_publish(project, refs)
        report["refused"] = False
    except ValueError as exc:
        report.update(refused=True, refusal=str(exc))
finally:
    ro_evidence.time.monotonic, ro_evidence.first_match = clock, match
Path("deadline-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
