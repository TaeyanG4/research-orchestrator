# Local fixture

Copy the wrapper to a disposable installed/hooks directory with installed/scripts/ro_hook_runner.py beside it and an agents.md in installed. Use paths containing spaces. Set RO_HOOK_PYTHON to a sentinel which records argv and stdin rather than running Python. Invoke sh ro-hook.sh PreToolUse from hooks, and invoke ro-hook.sh through PATH from a different directory. Record the selected runner path, event, stdin, exit status and bounded completion. No path to a real user installation belongs in the report.
