# guard — Handoff

This file records events and resume points. Read `<skill-root>/references/records.md` for record formats, `<skill-root>/references/sessions.md` for slot lifecycle, and `<skill-root>/references/compute.md` for `Active compute`.

## Shared state
- Not applicable: none

- Active agent(s): A
- Users: operator
- Current project state: initialized
- Current best: none yet
- Active compute: none
- Plan collection: idle
- Open consistency issues: none


## Active handoff — Agent sections

Each slot edits only its own section; other sessions read only its `Current host`, `Current user`, and `Current thread` lines.

### Agent: A
- Current host: unassigned
- Current user: none
- Current thread: none yet
- Resumable state: read discoveries, then the plan
- Blocker: none
- Next action: choose the highest-priority item you may work on

## Completed / review log

Preserve earlier sessions.

Append an event per completed item. Event format:

```markdown
### YYYY-MM-DD HH:MM — A — H-A-01
- Host: Claude Code | Codex | Antigravity | <other>
- User: <user name>
- Action: ...
- Result: <one line>; see <discovery ID>
- Artifacts: <paths> / none
- Discovery updates: D-A-001 / none — <reason>
- Review verdict: <discovery ID> CLOSED | HOLD | CHALLENGED / none
- Resource: CPU | GPU | Other | none
- Other executor: <executor> / none
- New plan items: H-A-02, H-A-03 / none — <reason>
```

## Archived history

When this file becomes hard to scan, move older completed-log detail to `docs/<focused-name>.md` and leave a short summary and link here.
