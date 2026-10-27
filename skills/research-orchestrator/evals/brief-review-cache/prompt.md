---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Reproduce review-cache invalidation in a disposable project using scenario.md. Initialize a work project with one dated decision-changing H-A-01/s1 event referencing result.txt. For this synthetic regression only, create the independent PASS receipt described in the scenario through the receipt API. Warm both an ordinary brief and a compact brief. In separate copies, (a) replace only that receipt with FAIL, (b) change only result.txt, and (c) change only a member of a reviewed directory. Capture the next ordinary and compact brief immediately, without clearing caches, touching the four coordination files, or waiting for expiration. Save raw responses, command logs and before/after hashes in cache-checks/. Explain the observed findings in cache-report.md. Do not launch jobs or real reviewers.

Input files: scenario.md
