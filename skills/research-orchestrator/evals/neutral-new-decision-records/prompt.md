---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Draft discovery records for the new research and competition projects using observations.json. Put them in research-discoveries.md and competition-discoveries.md, with one record per observation and an appropriate Decision class. These are drafts from supplied evidence, so do not run experiments or claim independent verification. Keep the archived v2 record in legacy-v2.md unchanged.

Also inspect the shipped examples and save their Decision class fields as example-classes.json, an array of objects with file (relative to examples/) and value keys. Explain briefly which vocabulary belongs in new records and why the old archival record can remain as written.

Input files: observations.json, legacy-v2.md
