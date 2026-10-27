---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check launch ownership in two local projects. Initialize classic-project with the quick preset and classic workflow, and unified-project with quick and unified workflow. Replace their plans with classic-plan.md and unified-plan.md respectively, and use the supplied handoff.md in both. Work as slot A throughout. Copy worker.py into each project.

In classic-project, try to launch H-B-01 using worker.py with rejected-classic.txt as its argument. In unified-project, try H-A-02 with rejected-foreign.txt and H-A-03 with rejected-unclaimed.txt. Keep their existing ownership unchanged. Before and after each attempt, record the existence and exact bytes of .ro/job-sequence.json and .ro/jobs.json, the command's exit status and output, and whether its marker file exists, in ownership-evidence.json.

Then launch your own classic H-A-01 and unified H-B-02 with own-classic.txt and own-unified.txt respectively. Monitor both jobs through their terminal outcomes, append their returned Job lines to the current handoff log, and include the successful job IDs and artifact contents in ownership-evidence.json. Explain which ownership rule each refusal or success demonstrates in summary.md.

Input files: classic-plan.md, unified-plan.md, handoff.md, worker.py
