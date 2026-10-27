---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a local work-project named Command certainty, using slot A, user operator and host local. Enable Enforcement block with Block jobs.mutate-bound and configure this operating system with the bash shell parser. Launch worker.py with bound/ as its run directory and confirmation 0s. Using ro check --dialect bash only, assess three command strings: cd scratch && rm '<absolute path to bound/input.txt>'; rm bound/input.txt && cd scratch; and cd scratch && rm input.txt. Do not execute these command strings.

Save cd-results.json with absolute_after, relative_before and relative_after objects, each containing exit_code, stdout and stderr from its check command. Preserve the input, stop the worker and record its monitor outcome.

Input files: worker.py, bound/input.txt, scratch/keep.txt
