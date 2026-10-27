import json, os, pathlib, signal, sys
sys.path.insert(0, sys.argv[1])
from ro_state import same_process
entries = json.loads((pathlib.Path(sys.argv[2]) / '.ro/jobs.json').read_text(encoding='utf-8'))
entry = entries[-1]
if not same_process(entry['pid'], entry['start']):
    raise SystemExit('supervisor identity is no longer current')
os.kill(entry['pid'], signal.SIGTERM)
print('Recorded supervisor terminated; worker cleanup still required.')
