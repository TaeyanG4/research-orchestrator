# Claude Code hook evidence - 2026-10-27

Withheld source SHA-256: `7654d7ac6d0fac0f7b44436ea8c74af89b78f6f18b53a03bb092466962c2d31e`.

| Probe | Event / check | Expected | Observed | Execution evidence |
|---|---|---|---|---|
| background | PreToolUse / `shell.background` | denied | denied | Attempt refused; no successful command execution |
| delete-bound | PreToolUse / `jobs.mutate-bound` | denied | denied | Attempt refused; bound file intact |
| benign | PreToolUse / none | no hook decision | no hook decision | Foreground command completed |
| read-bound | PreToolUse / `jobs.read-bound` | warned | warned | Foreground read completed |
| unmonitored-stop | Stop / `jobs.unmonitored` | warned | warned | Foreground command completed; Stop diagnostic recorded |
| future-record | PostToolUse / `records.timestamp` | warned | warned | Future record written; PostToolUse diagnostic recorded |

All six supplied probes matched their expected decisions. Claude Code 2.1.287, model `claude-haiku-5-5`, ran in `windows/bash` at 2026-10-26T18:58:04Z (2026-10-27 local date). Each probe used `<temporary-project>` with a synthetic registry bound to the harness's live process identity; no job was launched for that registry. The invocation loaded `<plugin-checkout>` through `--plugin-dir` without changing home configuration. Decisions come from `.ro/hook-diagnostics.jsonl`, checked alongside tool results and side effects; warning delivery in every UI and other events are outside this measurement. Paths are placeholders; session IDs, account data, tool inventories and native streams are withheld. This supplied candidate record does not verify subsequent repairs. The prior inconclusive summary was moved intact to `ro-evidence-archive/2026-10-27c/docs/host-dry-runs/claude-code-2026-10-27.md` (SHA-256 `88bdb8324761d0f6101f7610162702cb963719e33298d33b3ddc269e50c5e3e7`).
