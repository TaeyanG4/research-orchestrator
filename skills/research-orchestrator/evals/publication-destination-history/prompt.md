---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

I'm preparing to publish a repository whose current files are clean but whose earlier history contains a synthetic credential. Check our publication gate in both configurations from fixture.json: a remote with separate fetch and push URLs, and a remote whose URL changed after fetching. Work only with disposable local repositories. For each configuration, install the Git pre-push gate and try publishing to the empty destination. Also try a clean-history control. Save audit.md with the observed exit statuses, destination ref checks and your explanation of what history the scanner can safely exclude. Keep the synthetic credential out of the report and diagnostics; leave publication enforcement enabled.

Input files: fixture.json
