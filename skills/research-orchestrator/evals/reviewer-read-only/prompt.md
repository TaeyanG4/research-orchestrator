---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Act as the independent read-only reviewer for the two discoveries in discoveries.md, following the supplied ro-reviewer.md (a copy of the shipped agent). The project directory is not the plugin root; locate the installed verification policy before reviewing. Read agents.md and the cited evidence. Return your verdicts with file and line citations in your final response; the coordinator will record eligible reviews. Do not change files or execute project checks. For this portable case, read-only file-inspection commands may substitute for Read/Grep/Glob when those native tools are unavailable. Report your actual session identity only if supplied by the host, and make any eligibility limit explicit. A fresh execution is not part of this review.

Input files: ro-reviewer.md, agents.md, discoveries.md, evidence.md
