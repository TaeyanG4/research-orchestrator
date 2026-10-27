---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a work-project coordination workspace for a local data export check, claim an active item in slot A, and launch heartbeat_worker.py as an owned job in runs/recovery with expected duration 60s, confirmation 0s, heartbeat heartbeat.txt, and max silence 1s. Leave the fixture unchanged. It updates its heartbeat until pause-heartbeat exists in the run directory and ends when finish exists there, with a 60-second safety limit.

Create pause-heartbeat, run the job monitor until it reports the heartbeat stall, and save the registry as stalled-observation.json. Restart monitoring once while the heartbeat is still paused and record its result, so a restart alone cannot masquerade as recovery. Remove pause-heartbeat, verify that heartbeat updates resume, and restart monitoring. While the recovered monitor is still active, save the registry as recovered-observation.json. Then create finish, wait for the monitor's terminal outcome, and close the item and session with the returned Job line. Preserve the final registry and the fixture's result.json. Explain the incident and recovery in report.md, using the observed states rather than assuming that a restart worked. A successful result retains the original stall in history and records the eventual completion separately.

Input files: heartbeat_worker.py
