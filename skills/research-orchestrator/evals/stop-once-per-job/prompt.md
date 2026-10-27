---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Exercise Stop using the supplied disposable registry scenario and the installed adapter. Save each response in stop-results.json and explain whether it blocks or warns. Recreate the adapter between attempts to check that the behavior survives separate invocations. Keep the job registry intact; this is a local fixture test and needs no real worker or host application.

Save stop-results.json as an array containing the four raw JSON hook responses in order and retain the disposable project under project/.

Print the raw responses from the adapter calls to the command output as well, and retain any harness source used, so the saved report can be compared with the actual execution.

Input files: scenario.md
