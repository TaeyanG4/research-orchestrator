---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Initialize work/ from settings.json and keep its handoff compact. Run the checker and serialize its Issue objects as a JSON list with severity, check and field keys in work-check.json. Then create a research control under research/ with platform Shell and collector Shell/worker; remove only Current best, Active compute and Plan collection from that disposable control and save research-check.json. Explain the difference without disabling checks or adding empty work-summary fields.

Input files: settings.json
