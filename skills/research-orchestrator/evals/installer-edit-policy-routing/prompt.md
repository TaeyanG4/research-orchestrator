---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check the Claude Code project installer using the disposable configurations in scenario.md. Save the generated settings and a registrations.json table with one row per configuration, event, tool and command. Include both the manual registrations and the effective registrations after adding the enabled plugin's hooks, so duplicate invocations are visible. Repeat the installations and then disable the optional project policies, saving those results too. Save the supplemental partial-coverage and overlap checks in supplement-checks.json. Use local installer calls without starting a host or changing real user settings.

Input files: scenario.md
