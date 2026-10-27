---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review the six shipped examples as starting templates for a workshop. Follow brief.md, save the individual checker outputs under checks/, and write results.json with each example directory name mapped to ERROR, WARN and INFO integer counts. Do not silence checks, mutate source examples, or omit INFO. Save control-records.json mapping each measured model-change/input-change/combination discovery ID to its Control field, grouped by example.

Input files: brief.md
