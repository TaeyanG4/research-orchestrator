---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up a local work-project named Compute contenders, using slot A, user operator and host local. Prepare H-A-01 and H-A-02 with Resource CPU and Parallel NO, and separate run directories left/ and right/. Launch the supplied worker.py for each item from two concurrent local commands, each with expected duration 30s and confirmation 0s. Capture each command's exit_code, stdout and stderr in the results array of launch-results.json. Keep the original routing declarations.

Save the registry immediately after both commands return as reservation-snapshot.json, then stop the admitted job and record its monitor outcome. Explain which reservation prevented the other launch. Leave no worker running and retain the finished registry.

Input files: worker.py
