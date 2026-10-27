"""Local-only outward-action substitute; each execution is observable."""
import pathlib
import sys

log = pathlib.Path('attempts.log')
with log.open('a', encoding='utf-8') as stream:
    stream.write(sys.argv[1] + '\n')
raise SystemExit(int(sys.argv[2]))
