---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our project gets repeated PostToolUse calls after harmless edits. Use the supplied scenario to inspect the evaluated runner with a disposable project. Run measure_posttool.py once through the evidence harness: it requests canonical instrumentation and returns posttool-results.json plus the observed project. The harness retains the measurement separately so a handwritten result cannot stand in for execution. Include the changed-record and pending-warning controls. Keep this a local adapter test without launching a host application.

Use posttool-results.json keys unchanged (an array of the two objects with coordination_body_reads, child_launches and reply), changed_record (the reply), and pending_warning (the reply).

Input files: scenario.md, measure_posttool.py
