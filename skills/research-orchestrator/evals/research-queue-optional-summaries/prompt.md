---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the three disposable research projects in scenarios.json. Keep the collector-off projects compact; the team wants an explicit queue instead of numerical priority scores. Add the supplied hypothesis to the team's first slot without inventing scores. Do not run the study.

Keep the generated files under solo/, team/ and collector/. Save the initializer argument arrays in setup-results.json under those names. Remove only Current best, Active compute and Plan collection from the collector-enabled control after initialization. Run the checker on all three projects and save its Issue objects, including severity, check and field, as solo-check.json, team-check.json and collector-check.json.

After saving the control's checker result, reconfigure that same collector-enabled project and save its handoff as collector-reconfigured-handoff.md and its new checker issues as collector-reconfigured-check.json. Keep the earlier checker result for comparison.

Input files: scenarios.json
