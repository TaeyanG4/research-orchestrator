---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Initialize a research project in this folder with preset `solo-research`, platform `Claude Code` and user `operator`. Queue the item described in request.md as H-A-01 and claim it. Prepare the brief you would give a separate agent for its stage s1 and save it as brief.md; do not start that agent. The agent's reply is already in report.md: record the stage outcome in the project from it, then save the checker output as check.txt. Do not contact any remote service.

Input files: request.md, report.md, data/values.csv
