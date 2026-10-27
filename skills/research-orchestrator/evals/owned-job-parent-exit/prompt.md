---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a work-project coordination workspace for a local data export check. Claim an active item in slot A, create runs/parent-exit, and launch launcher.py as an owned job with that run directory, an expected duration of 60s, and confirmation of 0s. Leave the fixture unchanged. It starts a worker and exits; the worker continues until stopped or its 60-second safety limit.

After the launcher exits, verify that the worker remains supervised. Save the job registry at that point as parent-exit-observation.json. Exercise the configured bound-path hook for an attempted edit of runs/parent-exit/input.txt, and try closing the session while the worker is still running. Record the actual hook and close results in report.md. Then stop the owned tree, verify the worker has stopped, monitor the terminal outcome, and close the session. Preserve the registry, the worker's state samples, and the handoff Job line. The report should distinguish launcher exit, worker liveness, and job completion using the observed evidence.

Input files: launcher.py
