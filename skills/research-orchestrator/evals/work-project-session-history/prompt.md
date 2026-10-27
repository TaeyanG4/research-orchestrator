---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up this archive preparation project with the work-project preset in the current directory. I am operator, the host is local, the environment is windows/powershell, Git sync is off, and the remaining defaults are fine. Complete the two routine preparation tasks in brief.md in this one session, saving the initially queued plan as queued-plan.md before starting. trial.md reports a failed approach that future sessions need to avoid; keep that result available without repeating the trial. Do not convert the source files.

Record the trial discovery's Finding as a single-line JSON object with selection_rule ("suffix-only"), decision ("accept" or "reject"), required_inputs (all required filenames in alphabetical order), and omitted_inputs (filenames the rule dropped, in alphabetical order). This makes its reusable conclusion inspectable without rerunning the trial.

Close the session and save copies of the four coordination files under work-snapshot/. Then reconfigure the project to solo-research for a later investigation. Keep the work session's historical records intact, run the consistency checker, and leave a clear next-session action. Do not start the investigation now.

Input files: brief.md, trial.md
