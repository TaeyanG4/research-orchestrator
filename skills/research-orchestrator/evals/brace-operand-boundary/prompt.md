---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the Bash guard decisions for the commands in brief.md using the shipped parser and outcome function. Pass the command strings as data; do not execute them. Save brace-results.json with the exact command, each finding's check/uncertain/outcome fields, and the configured Block list. Retain the small driver used to obtain the results. Explain how brace operands affect path certainty and the separate trailing background operator.

Input files: brief.md
