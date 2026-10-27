---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

I want to install the publication gate for a component inside a larger Git repository. Check the disposable setup in scenario.md, trying the nested project path first and then the repository root. Save the exit status and filesystem changes from each installation, then demonstrate that the root gate rejects forbidden outgoing history and that losing its registration cannot silently allow publication. Include an unrelated repository sharing the same hook directory as a control. Use local test repositories and an isolated home; do not push to any external remote or start an agent host. Save the evidence in installation-checks.json and explain the repair command in result.md.

Input files: scenario.md
