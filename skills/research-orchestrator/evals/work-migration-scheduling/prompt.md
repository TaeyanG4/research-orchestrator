---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Move the archive-restoration queue described in brief.md from classic to unified and back using the bundled migrator. Initialize project/ with the work-project preset, Cedar Shell, one slot, self verification and Git off. Save project/plan.md as original-plan.md before migration, unified-plan.md after the first migration, and classic-plan.md after the second. Release the slot before each migration. Preserve the project and save final checker output as checker.txt.

Input files: brief.md
