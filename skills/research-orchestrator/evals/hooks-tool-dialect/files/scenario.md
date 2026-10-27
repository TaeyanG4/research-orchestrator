# Scenario

Use a disposable project with Environment: windows/bash, Enforcement: block and Block: jobs.mutate-bound. Register the current test process as a running owned job with runs/job-a/input.txt bound. Supply a PowerShell tool payload with command Remove-Item runs/job-a/input.txt and an explicit project cwd. Run only the hook adapter, never the cleanup command.
