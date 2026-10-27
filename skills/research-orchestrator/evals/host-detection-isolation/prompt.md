---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check quick-project setup under each host environment in hosts.json using disposable projects. For each child process, remove inherited CLAUDECODE, CLAUDE_CODE_*, CODEX_*, GEMINI_* and TERM_PROGRAM markers before applying the scenario markers. Set SHELL=/bin/bash, LANG=C, LC_ALL=C and LANGUAGE=ko so the launching terminal cannot choose the test defaults.

For each scenario, initialize default/ without --platforms. Try rejected/ with the other platform's collector but no --platforms. Then initialize explicit/ with that same collector and an explicit --platforms naming its platform. Reconfigure explicit/ under the opposite host's markers without platform or collector flags to check that stored choices survive. Keep the generated project files and save command arguments, exit codes, stdout and stderr for every invocation in results.json. Do not edit generated settings or change validation code to make a command succeed.

Input files: hosts.json
