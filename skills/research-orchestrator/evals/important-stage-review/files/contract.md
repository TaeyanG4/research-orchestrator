# Consequential stage contract
Stage: H-A-01/s2
Command: <python> stage_stub.py consequential
Inputs: stage_stub.py
Expected: append consequential exactly once to stage-executions.log, then exit successfully.
Limit: one CPU, three seconds; stop the owned job if it exceeds six seconds or reports an error.
No shared data or service is touched.
