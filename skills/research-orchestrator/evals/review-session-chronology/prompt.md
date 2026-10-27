---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the restored discovery ledger for a small archive project. Initialize project/ with hybrid verification, two slots on Cedar Shell and Maple Shell in multi mode, Git off and guards off, then use the supplied ledger as discoveries.md. Save the original checker response to before.txt. Preserve the recorded review history and use the supplied review notes to retain only supported VERIFIED states; no separate reviewer is available and none should be invented. Save the repaired project and after.txt, plus a short chronology.md explaining the accepted and rejected reviews.

Also check the two offset-bearing review timestamps in offset-checks.json against the supplied fixed clock, using the installed checker's chronology rules. Save their eligibility in input order as a Boolean array in offsets.json.

Input files: records.md, review-notes.md, offset-checks.json
