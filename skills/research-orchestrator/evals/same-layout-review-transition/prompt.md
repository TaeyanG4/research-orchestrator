---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Initialize a project with the initializer using setup.json, then copy queue.md to plan.md and discovery-records.md to discoveries.md. Run the checker and retain a snapshot. Reconfigure only Verification from self to independent-review, keeping Profile work and Workflow unified. Run the checker again and retain its response, command invocations, changed files and backups. No review has been performed yet. Preserve the existing queue and evidence, including continuation bullets.

Initialize a second project with the same setup and queue but use self-reviewed-discovery.md as its discovery record. Confirm it is valid under self verification, snapshot every project file, and attempt the same verification-only transition. Preserve its existing evidence and verdict; report any refusal and retain a before/after comparison.

Input files: setup.json, queue.md, discovery-records.md, self-reviewed-discovery.md
