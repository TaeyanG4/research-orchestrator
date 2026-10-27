# Session slots

A slot identifies a line of work, not the tool or model running it. Any host can continue a slot under the workflow's ownership rules.

A session that never loads the skill still starts from `agents.md`: its `## Working rules` restate the core's rules, setup and `--reconfigure` add `@agents.md` (Claude Code's import) to `CLAUDE.md` unless that file already names `agents.md` (`--no-claude-md` skips this), and SessionStart names the rules. Codex reads `AGENTS.md`, which is `agents.md` itself on case-insensitive file systems; on others, add a pointer there.

## Identity and assignment

- Name slots `A` through `Z`, then `AA` through `ZZ` in spreadsheet-column order. Use `A` for single-agent work; reuse released slots before creating another. Host, product, model, and free-form role names are not slot names, so IDs remain stable when tools change.
- A host is the platform, not its model. Record it as `Current host` for the slot and `Host` in each event and discovery.
- A user is the person running the session. Use one word of letters, digits, `-`, or `_`, distinct from slot, host, or model names. Record `Current user` next to `Current host` and `User` in every event.
- In an existing project, ask for the user name only if the session has not supplied it. If Shared state's `Users` has exactly one name, confirmation of that name is enough. Add a new user to `Users` at their first session.
- Treat a slot as free only when `Current host` is `unassigned` or `released`; every other value means taken. A stale slot remains taken until the user chooses to reclaim it: lack of recent activity does not prove its session ended.
- Use the user's slot or continue/parallel intent; otherwise resolve new-session ambiguity below before choosing a slot. In an unambiguous assignment, reuse free slots subject to the classic workflow exception. Create a new slot with its handoff section, Shared state's `Active agent(s)` entry, and any plan section the workflow needs, together.
- Set `Current host: <host>` and `Current user: <user>` when taking or resuming the slot. Add workers only for independent useful work; [compute.md](compute.md) defines capacity and scaling.

### A new session in an existing project

A crash can leave a slot's items and claims locked. Continuing that work or starting a parallel line is the user's intent, so do not infer it merely from which slot comes first. A slot is eligible when its `Current host` is `unassigned`/`released`, or its `Current user` matches the explicitly supplied project user (`user`/`RO_USER`, never the OS account).

Honor an explicit slot or continue/parallel intent without another question. Otherwise keep automatic assignment when exactly one slot is eligible and nothing is stale. In other cases, ask once if a taken slot is stale, several slots are eligible, or resumable work exists and continue versus parallel is unspecified. A taken slot is stale only when it has no protected job in `.ro/jobs.json` (including failed runners with live or unverified descendants) and its newest event/claim is older than `Stale slot after` (default `2h`; [setting values](settings-values.md)).

SessionStart and `ro brief` print compact candidate metadata: slot, `Current host`/`Current user`, last activity time, and running jobs. Startup may inspect event/claim timestamps and whether resume cues exist; leave other slots' detailed evidence and resumable prose unread. Ask the printed question with all options together, recommended continuation first: “Which slot should this new session use? Continue slot A (resume its Next action; reclaim it if its session has ended) [recommended]; Start a new slot for parallel work; Use slot <X>.” Substitute the recommended candidate for A. Do not select an option on the user's behalf.

When assignment is ambiguous and `Autonomy: away` or another policy forbids questions, start a new parallel slot without asking. Preserve every existing slot's claims, `Resumable state`, and jobs; record the new-slot choice and any stale candidate in the brief and handoff so the user can decide later.

After the user chooses to reclaim stale A, run `ro --session <native-host-session> --slot A brief --reclaim --host <host> --user <user>`. This records `Action: reclaimed slot A after stale session (user choice)` and updates ownership while preserving claims, `Resumable state`, and jobs. `--slot A` alone selects routing; it does not authorize reclaim. Pass an expressed continue/parallel choice through `brief --intent continue|parallel`; `--no-questions` applies a question-forbidding policy to assignment. Continue selects the recommended resumable slot; reclaim still needs the user's choice and `--reclaim`.

### Session routing

SessionStart registers a supplied native session ID after an unambiguous assignment or resolved choice. Automatic registration changes only tool routing, so still update handoff ownership when taking the slot.

For manual selection, run `ro --session <native-host-session> --slot B brief` (use your slot). Commands and hooks can also use `RO_SESSION` or Codex's `CODEX_THREAD_ID`. Keep `--session` or `RO_SESSION` on later commands when the host does not supply it. The project-local association lets commands and hooks find the same slot after child processes exit; changing a child shell's environment cannot update its parent hook environment.

An explicit `--slot` changes the association; otherwise the saved selection takes precedence over `RO_SLOT`. Commands that need ownership require a selected slot in a multi-slot project: supply `--slot`, set `RO_SLOT`, or use a registered session. `ro brief` and SessionStart can first resolve assignment through the decision above; an existing session keeps its saved association. This mapping routes tool state; handoff ownership still follows the rules above.

## Close a session

1. Finish completed items through the core's item lifecycle and reconsider the remaining items you own or claim. Rescore when using scores; in the `work` profile, finalize the one session event with its completed IDs and any reusable discoveries or follow-ups.
2. Finish reviews you claimed, or release them to their prior effective state as [verification.md](verification.md) specifies.
3. Update the slot's `Resumable state` and `Next action`, including any continuing job, so the next session can resume without reconstructing the conversation.
4. Before `ro close`, check every job your slot owns: refresh the registry with `ro jobs` and check host-managed background work, remote executors, and other unregistered jobs. If any running job is absent from the registry, do not run `ro close` or release the slot. Keep `Current host`, `Current user`, item and `Active compute` claims, and `Resumable state`; report which job is still running and why its missing registry protection defers closure. Run the checker directly while closure is deferred, and resume this procedure after the job ends.
5. Otherwise run `ro close` and resolve your checker findings according to the core. An empty queue with all slots idle writes `Paused:` to suspend direction cadence; remove it when resuming. Inspect the remaining claims and slot status; [operations-safety.md](operations-safety.md) defines the command's cleanup and running-job protection.
6. Sync the coordination files according to [git-sync.md](git-sync.md).
