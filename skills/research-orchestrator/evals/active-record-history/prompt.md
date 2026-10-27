---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Initialize a quick project with unified workflow and platform Shell in archive-project using slot A, then replace its generated plan.md and handoff.md with the supplied files. The archived copies are an audit trail, so preserve their bytes. Try to claim, release and launch H-A-01, which exists only in history. Claim H-A-02, release it, and claim it again. Run the checker and save its output in checker.txt. Launch H-A-02 with a short command that writes current-result.txt containing "current operator completed"; monitor the job through its terminal outcome and append its returned Job line to the current log.

As a live-conflict control, copy the project to conflict-project, add a live queue item H-B-01 claimed by B with Resource: CPU and Parallel: NO, add a taken slot B under Active handoff, and set Shared state's Active compute to CPU held by B for H-B-01 with the current timestamp. Try to launch A's H-A-02 there and record the refusal plus before-and-after sequence and registry bytes in conflict-evidence.txt. Preserve the archived sections in both projects.

Finally run brief and close archive-project's session. Save all command outputs and exit statuses in commands.txt, the brief immediately before close in brief.txt, and the close output in close.txt.

Input files: plan.md, handoff.md
