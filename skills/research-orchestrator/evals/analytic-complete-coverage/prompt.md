---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Create a solo-research project in project/ for the finite inventory audit in brief.md. Compute the total from every line of quantities.txt, register the measurement's coverage accurately, and save calculate.py, result.json and an unchanged quantities.txt together in one artifact directory (the output root or a subdirectory). Running calculate.py from that directory must read quantities.txt and recreate result.json; include numeric count and total fields, with optional extra metadata. Record the finding and scope limit in the project, preserving the input. Reserve an N ID for a short scope note in project/docs/scope-note.md and link it from Shared state. Check the project and save checker.txt. This session has no independent reviewer; leave any new discovery PENDING and do not wait for a reviewer.

Input files: brief.md, quantities.txt
