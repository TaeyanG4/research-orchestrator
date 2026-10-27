---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our two host sessions share one project and their hooks only send cwd and session_id. Use brief.md to create the project, associate native-first with slot A and native-second with slot B, and claim a separate item for each. Invoke the installed hook runner with SessionStart payloads containing those native IDs and no slot, and retain the distinct startup responses.

Then use native-second to launch worker.py as an owned job without repeating --slot. Keep RO_SLOT=A in the command and hook subprocess environment to reproduce the stale parent environment. Before monitoring, invoke Stop for native-first and native-second while the worker is live. Capture the job ownership, both responses, and exit codes. Stop the job, monitor its outcome, and repeat native-second's Stop. Also capture startup for a fresh unregistered native-third: it should explain how to choose a slot without showing either active slot's brief. In a separate disposable project, run one native-default command without selecting a slot and verify that the next native startup finds the default slot it used. Exercise a damaged association in that disposable project, retaining its visible hook diagnostic and repair by reselecting the slot.

Repeat native-second's startup with cwd-only hook input and its identity supplied separately through RO_SESSION and CODEX_THREAD_ID, retaining RO_SLOT=A. Also capture a cwd-only startup without either identity variable and RO_SLOT=B to check the single-session fallback.

Save exact command arguments, hook stdin, exit codes, stdout, and stderr in session-results.json; retain the project state and a concise summary. Use the shipped CLI and hook runner directly, without implementing replacement routing or fabricating hook responses.

Input files: brief.md, worker.py
