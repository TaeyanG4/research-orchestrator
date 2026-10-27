---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our research project has grown for months and startup reads are getting slow. Follow scenario.md to build the disposable project with its long history, then bring the startup reads back within their limits using the skill's own commands. Save under history-checks/: the checker output before archiving (check-before.txt), after archiving discoveries (check-after-discoveries.txt) and after archiving events (check-after.txt); the `ro index` output before archiving (index.txt); one archived discovery opened with `ro index <ID>` (opened.txt) and a `ro dupcheck` search that finds it (dupcheck.txt). Then restore archived discovery D-A-002 with the skill's command, add the sentence `Revised after a second run.` to its Finding, archive it again, and save `ro index D-A-002` as history-checks/rearchived.txt. Explain in history-report.md what moved, what stayed and why. Do not delete records or move entries by hand; the added sentence is the only manual edit.

Input files: scenario.md, make_history.py
