---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review validate.yml, a copy of our proposed release workflow. We need the release validator to run on Windows, Ubuntu, and macOS with Python 3.12 on pushes and pull requests. Confirm the actual matrix, interpreter, dependency setup, and validation command, and explain the workflow's permissions and credential use. Base the report on the file; do not claim that remote CI jobs ran. Do not change files.

Input files: validate.yml
