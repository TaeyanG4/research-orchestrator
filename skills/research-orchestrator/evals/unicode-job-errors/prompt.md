---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

A worker writes localized failure messages, and I need confidence that the monitor will notice a failure even when a write or polling read splits a UTF-8 character. Run the supplied replay against this skill's job scanner without editing either the replay or installed skill. Save its observed results as scan-results.json and explain in monitoring-review.md whether the first failure is reported once, whether a later failure is still detected, and what a monitor alert means for an active job's ownership. Do not launch any real workload or infer success from an incomplete character.

Input files: replay.py
