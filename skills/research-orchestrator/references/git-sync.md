# Git sync

Follow the section that `Git sync` in `agents.md` names. Several users on different machines need `push`; without it they cannot see each other's slots, items, or compute claims.

## In every mode

- Never run `git init` or add a remote yourself. If `commit` or `push` is set but the project is not a git repository (with a remote, for `push`), switch `Git sync` to `off` — edit the line and run `init_research_orchestrator.py . --reconfigure`, which also does this automatically — log the change as a handoff event with heading `none`, and tell the user so they can set up the repository and turn sync back on.
- Never force-push or rewrite history. Commit only the coordination files unless the user asks to include code or results. Never commit secrets, credentials, or large data.

## off

Do not run git for the coordination files. Sessions share state only through the files on this machine; sessions on other machines or other users' computers will not see each other — switch to `push` for that.

## commit

Right after each linked change (see [records.md](records.md)) and when closing the session, commit the coordination files you changed:

```bash
git add <changed files among agents.md plan.md discoveries.md handoff.md docs/>
git commit -m "ro(<agent>/<user>): <short action>"
```

Never push. Sessions on other machines will not see this state; use `push` for that.

## push

As `commit`, and also:

1. Run `git pull --rebase` before editing `plan.md`, `discoveries.md`, or `handoff.md`, and before launching a heavy job, so you see the latest items, claims, and slots.
2. Push right after each commit.
3. If the push is rejected, run `git pull --rebase`, keep both sides of any conflict in the coordination files (never drop another agent's lines), and push again. If a conflict touches anything else, stop and ask the user.
