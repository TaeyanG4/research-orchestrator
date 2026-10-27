"""Replay byte boundaries against the installed scanner; no worker or network."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--scripts", required=True)
args = parser.parse_args()
sys.path.insert(0, args.scripts)
import ro_jobs

error = "실패"
data = error.encode("utf-8")
results = {}
with tempfile.TemporaryDirectory() as folder:
    log = Path(folder) / "worker.log"
    original = ro_jobs.LOG_SCAN_BYTES
    try:
        ro_jobs.LOG_SCAN_BYTES = 7
        log.write_bytes(b"x" * 6 + data)
        entry = {"log": str(log), "errors": [error]}
        bounded = [ro_jobs._error_match(entry)]
        entry = json.loads(json.dumps(entry))
        bounded += [ro_jobs._error_match(entry), ro_jobs._error_match(entry)]
        with log.open("ab") as output:
            output.write(b"\n" + data)
        bounded += [ro_jobs._error_match(entry), ro_jobs._error_match(entry)]
        results["bounded_reads"] = bounded
        log.write_bytes(data[:2])
        entry = {"log": str(log), "errors": [error]}
        writes = [ro_jobs._error_match(entry), ro_jobs._error_match(entry)]
        entry = json.loads(json.dumps(entry))
        with log.open("ab") as output:
            output.write(data[2:])
        writes += [ro_jobs._error_match(entry), ro_jobs._error_match(entry)]
        results["later_write"] = writes
    finally:
        ro_jobs.LOG_SCAN_BYTES = original
Path("scan-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
