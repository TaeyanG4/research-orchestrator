---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In a disposable copy of the release source, exercise check_doc_encoding from scripts/validate_release.py against docs/nested/guide.md containing the supplied damaged text. Retain the exact rejection, restore the section sign, range dashes and arrow using the intended text, and record the clean result. Also check ordinary prose questions. Save encoding-report.md with commands, raw results and the before/after guide. Do not run pytest, behaviour cases, graders, host probes or viewers.

Input files: damaged.md, intended.md
