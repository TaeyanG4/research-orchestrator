"""Recompute a paired analysis and verify saved code in a fresh working directory."""
from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile

if __package__:
    from .proc import no_window_flags
else:
    from proc import no_window_flags

ANALYSIS_TIMEOUT = 10
MAX_RESULT_BYTES = 65536
CRITICAL_PATTERN = r"\bt_critical\s*=\s*([0-9]+(?:\.[0-9]+)?)"


def expected_replication(files: Path) -> dict:
    """Derive the oracle from the original observations and stated method."""
    with (files / "measurements.csv").open(encoding="utf-8", newline="") as source:
        differences = [float(row["after"]) - float(row["before"]) for row in csv.DictReader(source)]
    excerpt = (files / "paper-excerpt.md").read_text(encoding="utf-8")
    critical = re.search(CRITICAL_PATTERN, excerpt)
    if critical is None:
        raise ValueError("The canonical excerpt does not specify t_critical")
    mean = statistics.mean(differences)
    sd = statistics.stdev(differences)
    se = sd / math.sqrt(len(differences))
    margin = float(critical[1]) * se
    return {"n": len(differences), "mean_difference": mean, "sample_sd": sd,
            "standard_error": se, "t_statistic": mean / se,
            "ci95": [mean - margin, mean + margin]}


def matches_replication(result: object, expected: dict) -> bool:
    if not isinstance(result, dict):
        return False

    def close(actual, target):
        return type(actual) in {int, float} and math.isclose(actual, target, rel_tol=0, abs_tol=1e-6)

    interval = result.get("ci95")
    return (all(close(result.get(key), value) for key, value in expected.items() if key != "ci95")
            and isinstance(interval, list) and len(interval) == 2
            and all(close(actual, target) for actual, target in zip(interval, expected["ci95"])))


def _input_variants(files: Path) -> list[tuple[str, dict[str, bytes]]]:
    originals = {name: (files / name).read_bytes() for name in ("measurements.csv", "paper-excerpt.md")}
    reader = csv.DictReader(io.StringIO(originals["measurements.csv"].decode("utf-8")))
    rows = list(reader)
    # Vary both the location and spread of the paired differences. Changing the
    # number of rows also detects a hardcoded sample size in otherwise live code.
    for index, row in enumerate(rows):
        row["after"] = str(float(row["after"]) + (index + 1) ** 2 / 8)
    extra = dict(rows[-1])
    # Keep each observation's identity unique, so a replication that validates
    # paired identifiers does not reject an invalid perturbation fixture.
    identifiers = {row["pair_id"] for row in rows}
    next_id = max((int(value) for value in identifiers if value.isdecimal()), default=0) + 1
    extra["pair_id"] = str(next_id)
    extra["after"] = str(float(extra["after"]) + 1.75)
    rows.append(extra)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    excerpt = originals["paper-excerpt.md"].decode("utf-8")
    # The excerpt binds its method to n-1 degrees of freedom. A count-changing
    # probe must keep that declaration coherent, or correct input validation
    # looks like a hardcoded calculation. The supplied critical value remains
    # a method input; the separate method probe tests its use independently.
    observation_excerpt, replacements = re.subn(
        r"(For )\d+( degrees of freedom)",
        lambda match: f"{match[1]}{len(rows) - 1}{match[2]}", excerpt)
    if replacements != 1:
        raise ValueError("The canonical excerpt must declare its degrees of freedom once")
    observation_excerpt = observation_excerpt.replace("Eight paired observations", f"{len(rows)} paired observations")
    observation_excerpt = observation_excerpt.replace("all eight archived observations", f"all {len(rows)} archived observations")
    sensitivity_note = (
        "Synthetic arithmetic sensitivity control: the observations or supplied "
        "multiplier below differ from the archive. The source report's numbers "
        "and 95% wording are retained only as historical comparison text; the "
        "perturbed interval makes no statistical coverage claim. Apply the "
        "supplied multiplier arithmetically, without inferring a new quantile.\n\n")
    observations = {"measurements.csv": stream.getvalue().encode("utf-8"),
                    "paper-excerpt.md": (sensitivity_note + observation_excerpt).encode("utf-8")}
    critical = re.search(CRITICAL_PATTERN, excerpt)
    if critical is None:
        raise ValueError("The canonical excerpt does not specify t_critical")
    altered = excerpt[:critical.start(1)] + str(float(critical[1]) + 0.875) + excerpt[critical.end(1):]
    method = {**originals, "paper-excerpt.md": (sensitivity_note + altered).encode("utf-8")}
    return [("canonical", originals), ("changed observations", observations), ("changed critical value", method)]


def _rerun_variant(ctx, name: str, label: str, inputs: dict[str, bytes]) -> tuple[bool, str]:
    """Use copies, no previous result, bounded runtime, and discarded process output.

    This prevents accidental artifact reuse or edits during regrading; it is not
    an OS security sandbox for hostile Python.
    """
    root = ctx.outputs.resolve()
    entry = Path(name)
    if (entry.is_absolute() or ".." in entry.parts or entry.suffix != ".py"
            or not (root / entry).resolve().is_relative_to(root)):
        return False, f"Invalid analysis path: {name}"
    try:
        with tempfile.TemporaryDirectory(prefix=".replication-check-", dir=ctx.run_dir) as temporary:
            work = Path(temporary)
            # Preserve Python helper imports, but never copy a prior result that
            # would make a no-op script appear to reproduce the calculation.
            for source in root.rglob("*.py"):
                if not source.resolve().is_relative_to(root):
                    return False, "Analysis includes a Python symlink outside its saved outputs"
                target = work / source.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            if not (work / entry).is_file():
                return False, f"Missing saved analysis: {name}"
            for filename, data in inputs.items():
                (work / filename).write_bytes(data)
            expected = expected_replication(work)
            environment = {key: value for key, value in os.environ.items()
                           if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH"}}
            environment.update(TEMP=str(work), TMP=str(work), TMPDIR=str(work))
            # Isolated Python ignores user packages and PYTHONPATH. Explicitly
            # allow saved sibling helpers, as a normal script invocation would.
            bootstrap = ("import runpy,sys; from pathlib import Path; "
                         "sys.argv=sys.argv[1:]; "
                         "sys.path.insert(0,str(Path(sys.argv[0]).resolve().parent)); "
                         "runpy.run_path(sys.argv[0],run_name='__main__')")
            completed = subprocess.run(
                [ctx.python, "-I", "-c", bootstrap, str(entry)], cwd=work, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=ANALYSIS_TIMEOUT, check=False, creationflags=no_window_flags())
            if completed.returncode != 0:
                return False, f"{name} rerun exited {completed.returncode}"
            if any((work / filename).read_bytes() != data for filename, data in inputs.items()):
                return False, f"{name} changed the canonical inputs during its rerun"
            output = work / "replication.json"
            if not output.is_file() or output.is_symlink() or output.stat().st_size > MAX_RESULT_BYTES:
                return False, f"{name} did not recreate a bounded replication.json"
            result = json.loads(output.read_text(encoding="utf-8"))
            valid = matches_replication(result, expected)
            return valid, f"{name} rerun matches independently calculated {label} results: {valid}; expected: {expected}"
    except subprocess.TimeoutExpired:
        return False, f"{name} exceeded the {ANALYSIS_TIMEOUT}-second analysis timeout"
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        return False, f"{name} could not reproduce the analysis: {exc}"


def rerun_analysis(ctx, name: str) -> tuple[bool, str]:
    """Require the saved calculation to depend independently on both input files."""
    try:
        variants = _input_variants(ctx.case_dir / "files")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return False, f"Could not prepare replication inputs: {exc}"
    evidence = []
    for label, inputs in variants:
        passed, detail = _rerun_variant(ctx, name, label, inputs)
        evidence.append(detail)
        if not passed:
            return False, "; ".join(evidence)
    return True, "; ".join(evidence)
