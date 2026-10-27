---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a work-project workspace for a local export check. Take slot A and claim one item. Launch worker.py in runs/crash with input.txt bound and confirmation 0s. Copy the fixture into that run directory first. The worker has a 60-second safety limit. Once it is running, use crash_supervisor.py with the skill scripts directory and project directory as arguments; it terminates only the recorded supervisor after verifying its creation identity.

Save the refreshed registry as orphan-observation.json. Attempt an edit to the bound input through the configured hook, a conflicting second launch, item release, and session close while the worker remains alive. Record those actual results in report.md. Stop the owned tree with ro kill, verify the worker has stopped, monitor its terminal outcome, append the returned Job line, then close the session. Preserve the final registry as final-jobs.json.

Input files: worker.py, crash_supervisor.py
