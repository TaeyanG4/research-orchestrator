---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check whether a receipt can still approve our release bundle when its references subdirectory becomes unreadable. Run the supplied `receipt_probe.py <skill-root>/scripts` unchanged; it first prepares a valid local receipt and then injects an enumeration PermissionError for that nonempty subdirectory, so the check works without changing filesystem permissions. It attempts receipt creation, validation and a prepared local mock action. Preserve the bundle and the resulting receipt and ledger state. Inspect receipt-probe.json and write summary.md explaining whether each operation refused because enumeration failed and whether anything executed or changed. This is a local safety probe; the mock command only creates executed.txt if the wrapper permits it.

The probe also hashes a generated 65 MiB binary artifact as a readable positive control and removes that temporary artifact. Include its hash result in summary.md so a large artifact is distinguished from an unreadable tree.

Input files: receipt_probe.py, bundle/release.txt, bundle/references/source.txt
