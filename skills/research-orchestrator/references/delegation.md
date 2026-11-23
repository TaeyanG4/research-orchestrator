# Delegation

Read this before handing work to another agent: a sub-agent, another host's model, or a worker command-line tool.

A delegated agent is not given this skill, the project's `agents.md` or the delegating session's memory, and nothing ensures it reads them; only its brief is certain to reach it. In one competition's mistake log (2026-11), 91 of 194 entries named a delegated agent in their title: deleting other tasks' files, memory blow-ups, shell background runs, typed times, scripts edited mid-run, and inferred explanations copied into records as facts. Rules retyped into each brief kept drifting, so the header is generated.

## Brief header

- Start every delegated brief with the output of `ro brief --delegate <item>` (an item, `<item>/sN`, or `none` for a task outside the plan). The header states the rules and the report sections; do not retype them. Read-only reviews get one too: a review agent once wrote to the real project after a failed `mkdir`.
- Fill in the resource limits (CPU workers, RAM, GPU), any folder other than the default run folder, and the task. A brief that states no limits tells the agent to ask.
- `Brief requirements: general-purpose: ro-delegate: v1` is the default of every built-in preset except `quick`. The hook then warns when an Agent brief lacks the marker line; an omitted agent type counts as `general-purpose`, and read-only agent types are not covered. An explicit `none` keeps the check off.
- The check proves the marker is present, not that the agent followed the rules. Hooks do reach Claude Code sub-agent tool calls (observed 2026-11-22), so blocking checks still apply inside them. Codex has no agent-tool mapping (see [hooks-capabilities.md](hooks-capabilities.md)); there the header is the only carrier.

## Moving a report into records

- copy numbers from the report's source rows, together with their direction (before → after) and kind (upper bound, net gain, entry count), and cite the row;
- keep an inferred explanation marked as inferred until you check the code or data it relies on;
- register reported tools in `docs/tools.md`, and log reported mistakes where the project keeps them;
- write the records yourself with `ro event`, `ro set-field` or `ro close-item`; a delegated agent's ledger or preregistration draft carries no times.

## Delegating to another host's model

- A new task gets a new output path; reusing one resumes the old session, which keeps answering the old task.
- Pass absolute paths: a worker may resolve relative paths against its own folder.
- Check first that the worker can reach the resource the task needs (Docker, GPU, network); a sandbox often cannot. If not, split the work: the worker builds the tool, the owning session runs it.
- When a step needs the delegating session to act, end the task there; act, then start a reading task. A worker waiting inside one task for its parent's action waited hours unnoticed.
- Resume a slow or rate-limited worker instead of killing it and starting again; each restart opens a new session and loses its context.
- Let the delegation tool own its answer file; a brief that named the same file overwrote a long report.

## Host behaviour delegated agents meet

- A host may move a long foreground call to the background after a fixed time (about 180 seconds observed in Claude Code); wait in shorter calls, or use `ro launch` and `ro monitor`.
- Pipe watchers (`tail -f … | grep …`) can outlive their session; end the whole pipe, or use the host's monitor tool.
