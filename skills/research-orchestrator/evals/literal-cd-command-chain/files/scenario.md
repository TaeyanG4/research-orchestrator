# Literal directory matrix

Use declared linux/bash syntax, Enforcement: block, and Block: jobs.mutate-bound, shell.cd. Protect a fixture run directory runs/owned with a running registry entry; use parser-level fixture data without real process inspection. Check these strings as data:

- cd runs/owned && rm input.txt
- cd 'runs/owned' && printf ready && rm input.txt
- cd runs/sibling && rm input.txt
- cd $RUN_DIR && rm input.txt
- cd runs && cd owned && rm input.txt
- cd runs/owned && printf ready; rm input.txt
- printf ready && cd runs/owned

Use an absolute disposable project root and resolve registry run_dir against it. No command from this matrix should be executed.
