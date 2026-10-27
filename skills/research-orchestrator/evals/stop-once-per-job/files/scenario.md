# Stop sequence

Create a project for slot A with Enforcement: block and Block: jobs.unmonitored. Use one stable session token for all calls. Put finished J-A-0001 in .ro/jobs.json with no monitor outcome. Call Stop twice. Recreate the adapter, add finished J-A-0002 with no monitor outcome, then call Stop twice again. Give both jobs slot A. These are already exited fixture jobs, so no processes should be launched, killed, or registered as monitored. Preserve all four replies in sequence.
