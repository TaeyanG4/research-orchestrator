# Disposable installation checks

Create a local Git repository with a nested `packages/component` directory and a separate isolated home. Record project and home file hashes before trying `install.py --project packages/component` from the repository root. Use the installer's `--home` option for every install call.

After the nested attempt, install at the repository root. Configure `Enforcement: block`, `Block: publish.scan`, and `Publish scan: secrets` in the project's `agents.md` settings section. Commit clean content, then a synthetic credential shaped as `ghp_` followed by six copies of `a1B2`, then a clean replacement. Invoke the installed pre-push gate with valid ref lines covering the two outgoing commits. Record the gate's decision and redacted finding without publishing the synthetic value in the result.

Remove the root registration from the dispatcher's `registrations` directory and invoke the gate again, recording its status and recovery guidance. Create a second, uninstalled repository with `core.hooksPath` pointing at the first repository's hook directory, and verify that its own invocation is not mistaken for a damaged installation.
