---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a work-project workspace with one queued item. Leave slot A released with Current user: none. Try launching worker.py for that item with confirmation 0s, and preserve the refusal and the registry state in report.md. Verify that this attempt did not execute the worker or append a launch event. Then take slot A using a host and user already listed in the project settings, launch the same command, monitor it to completion, and record its outcome. Preserve the resulting handoff and report. Do not replace the worker fixture.

Input files: worker.py
