---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Export the supplied retained saved-run folder with the repository evidence exporter into evidence.zip, including produced task outputs. Do not run the task, a model, or a grader. Preserve the saved failed assertion and timings, verify the archive manifest, and write export-review.json with the exported and omitted member counts. Explain in limitations.md that this is inspection of saved outputs and no new paired runs were made for 6.0.0 by owner decision.

Input files: saved/case-a/with_skill/outputs/result.json, saved/case-a/with_skill/outputs/analyze.py, saved/case-a/with_skill/grading.json, saved/case-a/with_skill/timing.json
