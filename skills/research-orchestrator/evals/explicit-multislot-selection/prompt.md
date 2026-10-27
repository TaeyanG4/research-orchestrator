---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Create the two-slot local project described in brief.md. With RO_SLOT, RO_SESSION and CODEX_THREAD_ID absent, run ro next-id H with no --slot or --session. Save its exit_code, stdout and stderr as implicit in slot-results.json. Before any further allocation, save the ID reservation contents as implicit_ids in that same JSON object (an absent registry means {}).

Then register slot B using one stable session identity, and run next-id H again with that session identity but no --slot. Save the returned ID as registered_id in slot-results.json. Preserve both handoff slot sections; do not remove A to make the project unambiguous.

Finally capture SessionStart and Stop responses with cwd-only payloads and no slot or session environment. Save both responses under identity_free_hooks in slot-results.json. They should request selection without treating A as the owner. In a separate single-slot project, capture the same events and save single_slot_hooks to demonstrate the A fallback.

Input files: brief.md
