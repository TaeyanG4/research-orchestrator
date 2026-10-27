# External wrapper inspection

Create a disposable project using work-project, English, the detected platform and OS, local resources, no Git sync, slot A, session author, and user test-user. Set Enforcement to block, Block to external.gate, and External actions to regex:release-tool publish. Use the corresponding Bash or PowerShell environment for each payload.

The simulated command is release-tool publish artifact.txt. Its wrapper uses ro.py external with --artifact artifact.txt and --action X-A-001. The appended direct command has the same command text. No actual release tool or artifact is needed because only hook decisions are inspected.

Read prefixes from the installed ro_command.command_prefix generator for shell sh and shell powershell, so the check covers the prefix users receive from the runtime.
