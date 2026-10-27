---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In a disposable copy of the release source tree, run scripts/validate_release.py --skip-tests and save structural.txt. Use the three supplied documents as publication controls: copy them under docs/ one at a time, recording check_publication findings in controls.json, then move rejected documents outside the public tree without deleting them. Also record check_local_links findings after changing the core operational link to the obsolete anchor in notes.md and after restoring it. Save the archive inventory and hashes in archive.json. Do not run pytest, initializer scenario tests, models, graders, host probes or viewers.

Input files: builder-report.md, agent-prompt.md, design.md, notes.md
