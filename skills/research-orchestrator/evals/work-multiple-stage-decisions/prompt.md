---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the disposable work project described in brief.md and preserve the supplied observations as its history. Keep a compact session completion summary. After recording the observations, shorten that summary's Action and Result to a session-level overview without any stage IDs; retain the original evidence and observation times elsewhere in the history so the next session can reconstruct both decisions.

No independent reviewer is available; do not start one, invent receipts, or weaken review policy. Attempt H-A-01/s2 and H-A-02/s2 through `ro launch` using `<python> stage_stub.py first-dependent` and `<python> stage_stub.py second-dependent`, respectively, and save their actual responses. Run H-A-03/s2 with `<python> stage_stub.py routine` through the same launcher, monitor it to completion, and close the session. Save stage-report.md explaining the remaining review obligations with the three launch responses.

Input files: brief.md, observations.md, first-result.md, second-result.md, routine-result.md, stage_stub.py
