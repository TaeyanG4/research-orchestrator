"""Local response fixture: failed delivery still returns a remote acceptance ID."""
from pathlib import Path
import sys
from synthetic_tokens import boundary_chunks, tokens
for value in tokens():
    print(value)
    print(value, file=sys.stderr)
for chunk in boundary_chunks():
    sys.stdout.write(chunk)
    sys.stdout.flush()
    sys.stderr.write(chunk)
    sys.stderr.flush()
mode = sys.argv[1]
if mode not in {'success', 'failure'}:
    raise SystemExit('choose success or failure')
with Path('executions.log').open('a', encoding='utf-8') as output:
    output.write(mode + '\n')
if mode == 'success':
    print('remote-id: archive-accepted-482')
    print('receipt stored; response complete', file=sys.stderr)
else:
    print('remote-id: archive-uncertain-731')
    print('acknowledgement lost after acceptance; reconcile before retry', file=sys.stderr)
    raise SystemExit(7)
