"""Local response fixture: failed delivery still returns a remote acceptance ID."""
from pathlib import Path
import json
import os
import sys
mode = sys.argv[1]
if mode not in {'success', 'failure'}:
    raise SystemExit('choose success or failure')
action = 'X-A-001' if mode == 'success' else 'X-A-002'
journal = json.loads(Path(f'.ro/external-attempts/{action}.json').read_text(encoding='utf-8'))
with Path('attempt-state.jsonl').open('a', encoding='utf-8') as output:
    output.write(json.dumps({'action': action, 'status_at_start': journal['status'],
                             'journal_key': journal['idempotency_key'],
                             'child_key': os.environ.get('RO_IDEMPOTENCY_KEY'),
                             'deadline_seconds': journal['deadline_seconds']}) + '\n')
with Path('executions.log').open('a', encoding='utf-8') as output:
    output.write(mode + '\n')
if mode == 'success':
    print('remote-id: archive-accepted-482')
    print('receipt stored; response complete', file=sys.stderr)
else:
    print('remote-id: archive-uncertain-731')
    print('acknowledgement lost after acceptance; reconcile before retry', file=sys.stderr)
    raise SystemExit(7)
