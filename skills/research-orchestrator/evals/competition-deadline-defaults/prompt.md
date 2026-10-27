---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the three competition projects described in scenarios.json. For each, calculate a deadline 30 calendar days from today and provide it in the --competition value as a deadline=YYYY-MM-DD suffix. Use the competition-solo preset, English, linux/bash and user operator. The folders are outside Git. Use the mapped command defaults for the first project; preserve explicit disabled policies for the second. For the unknown platform, show the unanswered choice without creating project records. Then try reconfiguring a copy of the mapped project to hub/fixture-task with the competition-solo preset and no new external-action answer; retain its refusal and confirm its records remain intact. Retain the initializer invocations, responses and resulting agents.md files. Do not ask me to repeat choices that the adapter or deadline already supplies, and do not execute any external action.

Input files: scenarios.json
