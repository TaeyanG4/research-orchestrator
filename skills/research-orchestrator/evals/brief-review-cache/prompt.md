---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Reproduce review-cache invalidation in a disposable project using scenario.md. Initialize a work project with one dated decision-changing H-A-01/s1 event referencing result.txt. For this synthetic regression only, create the independent PASS receipt described in the scenario through the receipt API. Warm both an ordinary brief and a compact brief. In separate copies, (a) replace only that receipt with FAIL, (b) change only result.txt, (c) change only a member of a reviewed directory, (d) make one member or subdirectory of the reviewed directory unreadable, and (e) let a reviewed file grow between its measurement and its read. Capture the next ordinary and compact brief immediately, without clearing caches, touching the four coordination files, or waiting for expiration. Save raw responses, command logs and before/after hashes in cache-checks/; save the two compact briefs of variant (d) as cache-checks/unreadable-brief-1.txt and cache-checks/unreadable-brief-2.txt, and record variant (e) in cache-checks/growth.json as a list of objects with keys moment (before-open or while-reading), error and bytes_read. Explain the observed findings in cache-report.md. Do not launch jobs or real reviewers.

Input files: scenario.md
