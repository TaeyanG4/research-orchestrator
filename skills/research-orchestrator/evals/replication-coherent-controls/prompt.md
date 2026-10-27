---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the reproducibility of these three saved analysis programs. Each should read observations.json and method.json, compute sample size, mean, sample SD, and the interval mean +/- multiplier*SD/sqrt(n), and recreate result.json without a prior result. Test canonical inputs, changed observation values and count, and a separately changed method multiplier. Keep changed inputs internally consistent so a legitimate validation check is not mistaken for a hardcoded answer; these are synthetic sensitivity controls, not inferential confidence claims.

Run each candidate on fresh disposable copies with no previous result and compare against your own calculation. Save audit.json listing accepted and rejected programs, each control's input values, exit status and numeric comparison, and save the stdlib Python audit. Preserve the source programs and inputs. No external services are available.

Input files: observations.json, method.json, input-driven.py, fixed-count.py, fixed-method.py
