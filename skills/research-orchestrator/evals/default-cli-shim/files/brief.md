# Fixture brief

Create three disposable homes named default-home, optout-home and compatibility-home. Install only the Claude Code runtime into each with --home and --no-hooks. Use no shim flag, --no-shim and --shim respectively. Do not alter PATH or real user configuration.

In install-results.json use keys `default`, `optout`, `compatibility`; each contains `arguments` (array), `exit_code`, `shim_exists` (boolean). For default also retain `help_exit_code` and `help_stdout`.

For a scope control, create two disposable project folders and install both using a fourth shared disposable home. The second installation owns that home's shim. Uninstall the first project normally, retaining the shim SHA256 before and after under `scope_control.before`, `scope_control.after` and the uninstall exit under `scope_control.exit_code`.
