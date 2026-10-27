# Disposable wrapper layouts

Create unrelated/ and project with spaces/one/two/. Only project with spaces/agents.md is a file. Clear inherited CLAUDE_PROJECT_DIR, CODEX_PROJECT_DIR and RO_HOOK_PYTHON before setting each scenario's values.

Exercise: unrelated cwd without hints; unrelated cwd with absent hints; a directory named agents.md instead of a file; nested project cwd without hints; unrelated cwd with CLAUDE_PROJECT_DIR pointing at the nested directory; unrelated cwd with CODEX_PROJECT_DIR pointing there. The no-project paths return JSON {} with no interpreter invocation. The project paths call the sentinel once and preserve a newline-terminated JSON stdin payload and the original working directory. Treat unavailable shell wrappers as untested, not passing.
