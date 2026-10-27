"""Reconstruct published scores from saved verdicts; never execute or grade cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import zipfile


def reconstruct(archive_path: Path, namespace: str = "adjudicated") -> dict:
    included = {"with_skill": {}, "old_skill": {}}
    totals = {key: [0, 0] for key in included}
    excluded = 0
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            if len(parts) != 4 or parts[0] != namespace or parts[-1] != "grading.json" or parts[2] not in included:
                continue
            grade = json.loads(archive.read(name))
            if grade.get("excluded"):
                excluded += 1
                continue
            expectations = grade["expectations"]
            passed = sum(row["passed"] is True for row in expectations)
            total = len(expectations)
            if not total:
                raise ValueError("Unexcluded grade has no assertions")
            if grade["summary"]["passed"] != passed or grade["summary"]["total"] != total:
                raise ValueError("Stored summary differs from individual verdicts")
            included[parts[2]][parts[1]] = passed / total
            totals[parts[2]][0] += passed
            totals[parts[2]][1] += total
    matched = sorted(set(included["with_skill"]) & set(included["old_skill"]))
    return {"namespace": namespace, "excluded_runs": excluded, "matched_cases": len(matched),
            "included_runs": {key: len(rows) for key, rows in included.items()},
            "assertions": {key: {"passed": row[0], "total": row[1]} for key, row in totals.items()},
            "matched_mean_percent": {key: round(statistics.mean(rows[case] for case in matched) * 100, 2)
                                     for key, rows in included.items()},
            "unmatched_mean_percent": {key: round(statistics.mean(rows.values()) * 100, 2)
                                       for key, rows in included.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--namespace", choices=("original", "adjudicated"), default="adjudicated")
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.archive, args.namespace), indent=2))
