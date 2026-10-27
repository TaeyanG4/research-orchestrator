---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the saved evaluation candidates in grades.json before we report the study's performance. Use the source assertions in assertions.json as the authoritative case definition; each candidate includes frozen metadata and its reported grade. Accept a candidate only if every source assertion has exactly one boolean verdict with nonempty textual evidence and its reported summary agrees with the verdicts. This keeps unsupported scores from becoming research conclusions.

Save audit.json with included and excluded candidate names, reasons for each exclusion, a summary computed from each included candidate's verdicts, and the mean pass rate across included candidates. Include each accepted candidate's duration, token, and execution-error measurements and their means; retain missing measurements as null and average only known values, since an unmeasured run is not a zero-cost run. Null optional execution metrics or user notes do not invalidate otherwise complete grades. Exclude candidates with out-of-range rates or measurements that cannot be represented as finite nonnegative numbers, so corrupt numeric evidence cannot stop the audit or distort its means. Also save the stdlib Python calculation so another researcher can repeat the audit on changed input files. Preserve both inputs and explain any uncertainty in the final response. This is a bounded evidence audit; no live model evaluations or external services are available.

Input files: assertions.json, grades.json
