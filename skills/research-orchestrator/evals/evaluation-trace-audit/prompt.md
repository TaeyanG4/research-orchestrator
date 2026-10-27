---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit these saved evaluation traces before we publish a research comparison. The previous detector treated any path containing an evals directory as contamination. Use trace-cases.json to distinguish genuine access to protected material from an assigned runtime under that directory, an absent ancestor-instruction probe, or a program argument mistaken for a file name.

The path variables and file snapshots describe the recorded environment, not this computer. Inspect the records without executing their commands. Source-repository reads, installed-skill access, hidden graders, and another run's files remain grounds for exclusion. Recover a prior exclusion only when the trace reproduces the original operation and shows why its path classification was wrong; a missing trace or a runtime-integrity finding remains excluded. This preserves useful evidence without turning uncertainty into a clean result.

Save audit.json with included and excluded scenario names and one reason tied to a specific event or retained finding for every decision. Also save a stdlib Python audit script that recreates the classifications from the input file. Preserve the input and explain the evidence limits in the final response.

Input files: trace-cases.json
