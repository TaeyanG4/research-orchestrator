# Tool registry

Read this before writing, copying, or changing a reusable script, and when the checker reports a `tools.*` finding. Sessions that cannot see each other's tools rebuild them: a second copy drifts from the first, and results produced by different copies stop being comparable. One registry entry per tool lets every session find, reuse, and extend the same code.

## Where it lives

The registry is `docs/tools.md`. Create it with `ro tools --init`, which writes these rules as its header, when the first reusable script appears: anything run more than once, by another session, or for evidence another record cites. One-off probes and generated files do not need entries. The four coordination files stay unchanged; link the registry from Shared state or an event if a reader needs it.

```markdown
# Tools

## submit-once — one guarded upload per candidate
- Path: tools/submit_once.py
- Version: 1.3.0
- Usage: python tools/submit_once.py <file> --message "<text>"
- Tests: tests/test_submit_once.py
- Status: active
- Updated: 2026-10-20
```

`Path`, `Usage` and `Status` are required. `Path` is the file or directory in the project, or `none` for an external command named in `Usage`. `Status` is `active`, `superseded by <tool name>` or `retired`. Optional fields include `Version`, `Tests`, `Files` (helper files the entry covers, comma-separated), `Inputs`, `Outputs` and `Updated`. Write the purpose in the heading so searches find it.

## Before writing a script

1. Search: `ro tools <purpose words>` lists matching entries; `ro dupcheck <terms>` also finds them beside plan items and discoveries.
2. Reuse an active entry when it does the job. When it nearly does, change it in place, bump `Version`, and update `Usage` and `Tests`; re-run its tests so existing callers keep working.
3. Copy only when a running job or a cited result depends on the old bytes. Then give the copy its own entry and mark the old one `superseded by <new name>`, so nobody extends the old copy by mistake.
4. Register a new tool in the same change that adds it, with a test or a recorded check when its output feeds evidence.

## Checker findings

The checker reads the registry only when `docs/tools.md` exists. It warns when an entry lacks a required field or names an unknown status (`tools.field`), when an active entry's path is missing (`tools.path.missing`), when two active entries share a path (`tools.path.duplicate`), and when a script sits beside a registered tool without an entry or a `Files` mention (`tools.unregistered`). Scripts are files ending in `.py`, `.sh`, `.ps1`, `.bat`, `.cmd`, `.js`, `.mjs`, `.ts`, `.R`, `.jl`, `.rb` or `.pl`; names starting with `_`, `.` or `test_` are skipped. Only directories that already hold a registered path are scanned, so code elsewhere in the project is not treated as a tool. `ro brief` reports how many tools are registered.
