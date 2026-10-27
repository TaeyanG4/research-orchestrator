Use the installed ro-hook.cmd on Windows or ro-hook.sh on POSIX. Keep the shell
executable's absolute path before restricting PATH in the child environment.

Create agents.md with Enforcement: block, Block: shell.background and the actual
OS with bash as its declared shell. Replay this input with an absolute project cwd:
{"tool_name":"Bash","tool_input":{"command":"echo sample &"}}

The only processes needed are the wrapper, its shell, and the selected Python.
