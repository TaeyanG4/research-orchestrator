---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the local coordination project described in brief.md. I want to check its running-job protection without deleting anything. Launch worker.py as an owned job with bound/ as its run directory, then submit PreToolUse hook payloads for the removal of input.txt: first with envelope cwd set to bound/, then with envelope cwd at the project root and tool_input.workdir set to bound/, then from scratch/. Also probe ../bound/input.txt from scratch/, and input.txt with no cwd or workdir information. Use absolute paths in the cwd/workdir fields and the shell declared for this host. These are hook probes only; do not execute any removal command.

Save each payload and hook response in probe-results.json. Explain which file each relative operand identifies and what the uncertain-directory response establishes. Preserve both input files, terminate the owned worker, and record its monitor outcome before finishing.

Input files: brief.md, worker.py, bound/input.txt, scratch/input.txt
