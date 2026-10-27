---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our pre-push gate times out, and I need recovery instructions from the gate's response. Create a disposable project with two small clean Git commits, Enforcement: block, Block: publish.scan, and Publish scan: secrets. Run the unchanged public_gate_replay.py with --scripts pointing to the installed skill's scripts directory and --project pointing to the disposable project. It simulates both a timeout after enumeration and one before the outgoing count is known, without contacting a remote. Keep its public-gate-report.json, apply the exact retry deadline from the after-enumeration response while preserving secret scanning, then run the helper again with --normal. Write recovery.md explaining the two refusals and the normal retry result. Do not push or change the installed skill; distinguish simulated failures from the normal scan.

Input files: public_gate_replay.py
