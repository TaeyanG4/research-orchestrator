---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

We copied the skill to a shared workstation and need to explain which protections our hosts actually deliver. Use the installed skill references and scenario.md to prepare capability-summary.json. The repository evidence docs are unavailable here. Do not run hosts, probes, installers or commands from the scenario.

For each check listed in the scenario, return an object under checks with adapter, claude and codex. Use E/W or W for adapter, and denial, warning, unverified or unmapped for the observations. Add codex_persisted_trust_verified and later_repairs_verified booleans, plus source_reference as the skill-relative path of the reference containing the matrix. Distinguish supported checks from dated observations; absence of a probe does not prove lack of support.

Input files: scenario.md
