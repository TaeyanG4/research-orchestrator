# Teammate setup

We use codex-cli 0.154.0 exec on Windows with PowerShell. The project already has
a .codex/config.toml with team settings. Python 3 is installed. The sample hook
files and the release checkout with install.py are available, and another teammate reported an active startup self-test.

Before adopting this setup, we need to know whether it protects running-job
files from deletion and rejects shell background calls. We also care about read
warnings and Stop monitoring notices. Please use the maintained hook reference
to explain which claims the recorded host run actually supports and how to work
while capabilities remain unverified.
