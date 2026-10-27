---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a quick local project called batch coordination, using the current shell environment, English, and operator in slot A. Add H-A-01 for the supplied batch worker. Launch worker.py through ro launch from the project root without --run-dir, with --bind inputs.txt and --confirm 0s. While the worker is still alive, verify the edit guard for plan.md, handoff.md, discoveries.md, worker.py and inputs.txt. Save binding-checks.json with the registered bound paths and the returned check IDs for each of those five edit targets. Record the launch notice and update the coordination files with the monitoring status. Before cleanup, launch a second owned copy of worker.py using --input inputs.txt and separate --run-dir; retain the initial --bind conflict refusal as evidence, then after stopping and monitoring the exclusive first job launch two copies sharing --input inputs.txt and distinct run directories. Record concurrent job IDs and the expected refusal for overlapping output bindings. Keep the worker and input unchanged, then stop the owned job, monitor it and close the session. Explain which paths were protected and why coordination edits remained possible.

Before the two shared-input trials, declare both plan items Parallel: YES and check that the two timer workers fit the local capacity. Keep the earlier exclusive-binding refusal unchanged; parallel compute permission does not permit overlapping output paths.

Input files: worker.py, inputs.txt
