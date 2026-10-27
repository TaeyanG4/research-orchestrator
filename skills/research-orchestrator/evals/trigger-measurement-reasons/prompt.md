---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the saved skill-selection study in measurements.json before we decide whether to revise our research workflow. Produce classifications.json with each query's prediction, the repeat number and reason for every inconclusive result, and aggregate confusion counts and coverage. Use the final attempt of each repeat; an earlier failed retry does not invalidate a clean recovery. All declared repeats need a clean endpoint and boolean measurement for a query to be scored. Apply the input's trigger threshold and required repeat count.

Keep contamination, timeout, rate limit, setup failure, and missing repeats distinct so we can choose the right next experiment. If contamination and timeout coexist, report contamination and name its access finding. A failed source-path guess marked noncontaminating is not an exclusion. Preserve unknown predictions as null: a skill read during an old full-task timeout does not establish the clean endpoint required by that experiment. Do not retrospectively trim the trace at that read. Treat contradictory run summaries, malformed attempt metadata, missing measurements and missing repeats as inconclusive rather than accepting a score or abandoning valid queries. Save a stdlib Python calculation that reads the input so another researcher can reproduce the audit on changed measurements, and preserve the input bytes. This is a bounded audit with no live models or network access.

Input files: measurements.json
