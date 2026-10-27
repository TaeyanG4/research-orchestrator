# Fixture brief

Create a disposable Git repository and home. Before installation put a foreign formatter hook in the project's Claude settings. Use the repository's install.py with project and home arguments. Keep all artifacts and command outputs within the disposable work area.

Use `foreign-formatter` as the foreign command. In uninstall-results.json retain `before` and `after` as relative-file-to-SHA256 maps covering home and project; `refusal` and `ordinary_uninstall` each contain `arguments` (array), `exit_code`, `stdout`, `stderr`. Include parsed `settings_after_uninstall`.
