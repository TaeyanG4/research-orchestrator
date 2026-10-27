---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the project in brief.md and launch worker.py as an owned job with runs/job-a as its run directory. I need evidence that PowerShell renaming the parent directory is protected. While the worker is live, submit hook probes for `Rename-Item -LiteralPath runs -NewName previous-runs`, the equivalent absolute source path, and `Rename-Item -LiteralPath runs/job-b -NewName previous-job`. Give each payload an absolute project cwd. These are PreToolUse probes only: do not execute a rename. Save the payloads and responses in rename-probes.json, and explain their decisions. Preserve the input files, terminate the worker, monitor its final result and record the outcome before finishing.

Input files: brief.md, worker.py, runs/job-a/input.txt, runs/job-b/input.txt
