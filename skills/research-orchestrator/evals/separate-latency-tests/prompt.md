---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review the supplied pytest.ini and validate.yml. Save test-policy.md with the default deterministic pytest command, the separate explicit latency command for the installed runner and in-process checks, and how CI keeps those runs separate. State precisely what can be concluded about timing from these configuration files. Do not run tests or claim any new measured latency.

Input files: pytest.ini, validate.yml
