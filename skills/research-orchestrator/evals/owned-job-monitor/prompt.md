---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Resume slot A as operator on local. Complete H-A-01 by launching and monitoring the supplied simulate_job.py as an owned long-running job. This local simulation lasts about eight seconds, creates runs/owned/job-result.json, and samples coordination state while it runs. Leave the script unchanged. Use runs/owned as its run directory, an expected duration of 8s, and a confirmation interval of 0s so the short simulation can exercise the launch workflow.

Keep the slot, item claim, and compute ownership until the job has ended and its monitor outcome is recorded. Observe completion through the job monitor, preserve its job registry evidence and handoff Job line, record the result, then check and close the session. Do not close or release the slot before the monitor outcome is recorded and do not prune the finished job registry entry.

Input files: agents.md, discoveries.md, handoff.md, plan.md, simulate_job.py
