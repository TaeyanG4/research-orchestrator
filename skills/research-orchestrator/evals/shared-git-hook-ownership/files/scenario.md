# Disposable shared-hook layouts

1. Create a repository and a linked worktree, with a configured publication policy
   in each checkout. Install Claude Code in the first and Codex in the second.
2. Create two independent repositories with the same absolute `core.hooksPath`.
   Install Claude Code in one and Codex in the other.

For each layout retain the second registration's bytes before removing the first.
Use `Enforcement: block`, `Block: publish.scan`, and `Publish scan: secrets`.
Do not push to any remote; invoke the local Git hook with malformed ref input.
For the custom-hook check use a disposable script containing a distinct comment.
