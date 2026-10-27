---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review these shell commands before I use them to run short parallel analysis jobs. Use the skill's `ro check` preflight to assess each command in commands.json as command text; do not execute the worker commands. Use temporary project settings with Enforcement: block, Block: shell.background,shell.detach, and a declared shell matching each case. Save wait-review.json with each input id, exit_code, check IDs and a short explanation. Explain which commands keep the tool call alive until all jobs finish, which can return while jobs still run, and why a final wait cannot erase an explicit detach operation.

Input files: commands.json
