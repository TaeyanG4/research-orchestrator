---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Classify each saved checker output in checker-outputs.json as clean or not clean for a release that allows INFO but no warnings or errors. Save verdicts.json with a boolean clean for each ID. Do not run a model or grader.

Input files: checker-outputs.json
