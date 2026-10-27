# Publication safety

Read this before configuring `Publish scan` or publishing Git history. The authoritative gate checks outgoing history because a cleaned working tree can still leave sensitive material in an earlier commit.

## Scan policy and coverage

Publication checks match built-in secret patterns plus optional `Publish scan` entries such as `secrets; literal:restricted text; regex:internal_[0-9]{1,32}`.

The PreToolUse publish pre-check examines at most 2 MiB of staged additions and only warns, even with `publish.scan` in `Block`: staged work may be unrelated to the commits being pushed. Only the Git hook scans every outgoing commit, including commit messages, paths and nested annotated-tag messages, and redacts findings with path/line and commit identifiers. That authoritative gate stays fail-closed. Authoritative Git reads disable replacement objects. Exclusions use only destination tips supplied by Git's pre-push invocation and available locally. Local tracking refs prove nothing about the push destination: fetch/push URLs can differ, and remote URLs can change. New refs scan reachable history conservatively; `--remote <name>` adds no exclusions. Objects are read in batches; clean-object results are cached by policy and object identity. It cannot discover secrets hidden by encoding or an unknown format.

`Publish scan` regexes accept literals, character classes, anchors and top-level flat alternatives, with at most one bounded single-atom quantifier (`?`, `{n}` or `{m,n}`, maximum 256) per alternative. For example, `regex:^token_[a-z]{8,32}$|^key_[A-Z]{12}$` is supported. All groups, including noncapturing groups, nested or unbounded quantifiers, lazy or possessive quantifiers and wildcard `.` are refused; escape metacharacters to match them literally. The setting's error describes this subset. Each branch is validated once before compilation. A literal or pattern match never prints the matched bytes.

The staged pre-check has eight seconds. The authoritative scan starts with sixty seconds for enumeration, then adds 0.05 seconds per outgoing object, capped at one hour, so larger histories have time to be inspected. An explicit setting such as `Publish scan: secrets; deadline=2m` replaces that default. The deadline is checked between windows, patterns and Git operations; exceeding it refuses an unscanned push. Refusals report the outgoing object count and an exact `deadline=` setting to apply before retrying. If enumeration itself times out, the count is reported as unavailable; the gate never invents coverage.

## Install the execution gate

Run `python install.py --project <dir>` to register the checkout with a shared pre-push dispatcher. Each checkout owns its registration, including linked worktrees and repositories sharing `core.hooksPath`; uninstall removes only that checkout's registration. Existing custom or legacy hooks stay intact and require manual integration: use `hooks/pre-push.sample`, replace its fixed plugin path and interpreter, and preserve the existing checks. Pass Git's exact ref lines on stdin to `ro hook pre-push --remote "$1"` and make the hook executable where required. The gate works independently of the agent host. Keep the full outgoing-history scan enabled so removed material is still checked.

Under `Enforcement: block` with `publish.scan` in `Block`, an unavailable outgoing scan returns nonzero; missing or unreadable policy also refuses an unscanned push, with restore/retry guidance. Explicitly disabled enforcement passes. The hook script itself exits nonzero if its interpreter is missing. Per-call host hooks cannot provide that failure protection; their enforcement and warning channels are in [hooks.md](hooks.md).

Verify the gate with a local push into a disposable local remote containing a planted secret in an intermediate commit. Use synthetic credentials for this test.
