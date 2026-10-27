---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Initialize a work project in this folder with preset `work-project`, platform `Claude Code` and user `operator`, keeping the supplied tools/ and docs/tools.md. Then handle request.md. Save the finished project's checker output as check.txt. Afterwards, in a disposable copy of the project, add tools/submit_v2.py without a registry entry and save that copy's checker output as control-check.txt. Do not contact any remote service.

Input files: request.md, docs/tools.md, tools/submit_once.py, tools/submit_common.py
