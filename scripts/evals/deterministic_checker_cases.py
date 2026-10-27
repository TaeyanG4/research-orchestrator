"""Artifact and checker assertions for review, scheduling and external-action cases.

These checks inspect saved results or rerun the deterministic project checker. They never
run a task command, a mock service, a reviewer, or a behavior evaluation.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import hashlib
import re
import shlex
import subprocess


def helpers():
    if __package__:
        from . import checks
    else:
        import checks
    return checks


def fields(text):
    return helpers().fields(text)


def records(text, prefix):
    return {key: fields(value) for key, value in helpers().blocks(text, prefix).items()}


def result(value, evidence):
    return bool(value), str(evidence)


def read(ctx, name):
    return ctx.text(name)


def clean_text(text, info=False):
    # One strict parser for every grader: clipped, unreadable or invented summaries are not clean.
    return helpers().summary_clean(text, info)


def checker_result(text):
    """A real checker summary, possibly with findings; unreadable or invented output is not one."""
    return helpers().summary_counts(text) is not None


def issue(text, check, severity=None, contains=()):
    return any(re.match(rf"^(?:- )?{severity or '(?:ERROR|WARN|INFO)'} {re.escape(check)}\b", line)
               and all(token in line for token in contains) for line in text.splitlines())


def check_report(name, check=None, severity=None, absent=(), clean=False):
    def run(ctx):
        text = read(ctx, name)
        ok = (not check or issue(text, check, severity)) and all(not issue(text, key) for key in absent)
        if clean:
            ok = ok and clean_text(text)
        return result(ok, text)
    return run


def milestone_unfinished(ctx):
    text = read(ctx, "after.txt")
    state = fields(read(ctx, "project/handoff.md")).get("Milestones", "")
    return result(issue(text, "guard.phase.milestone") and "10 blocked" in state and "25 pending" in state,
                  {"milestones": state, "checker": text})


def milestone_complete(ctx):
    text = read(ctx, "complete.txt")
    state = fields(read(ctx, "completed-control/handoff.md")).get("Milestones", "")
    complete = all(re.search(rf"(?:^|;)\s*{share}%?\s+complete\s*(?:;|$)", state) for share in (10, 25, 75))
    return result(complete and checker_result(text) and not issue(text, "guard.phase.milestone")
                  and not issue(text, "guard.phase.state"), {"milestones": state, "checker": text})


def migration_order(ctx):
    orders = {name: list(records(read(ctx, name), "H")) for name in ("unified-plan.md", "classic-plan.md")}
    return result(all(order == ["H-A-01", "H-A-02"] for order in orders.values()), orders)


def migration_next(ctx):
    headers = {name: read(ctx, name).split("\n## ", 1)[0] for name in
               ("original-plan.md", "unified-plan.md", "classic-plan.md")}
    return result(all(re.search(r"^(?:- )?Next: H-A-01\s*$", text, re.M) for text in headers.values()), headers)


def lean_queue(ctx):
    text = read(ctx, "project/plan.md")
    header = text.split("\n## ", 1)[0]
    items = records(text, "H")
    omitted = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority",
               "Resource", "Parallel", "Other"}
    return result(set(items) == {"H-A-01"} and re.search(r"^(?:- )?Ordering: queue$", header, re.M)
                  and re.search(r"^(?:- )?Next: H-A-01$", header, re.M)
                  and not omitted.intersection(items["H-A-01"]), {"header": header, "items": items})


def invalid_queue(ctx):
    text = read(ctx, "invalid.txt")
    return result(issue(text, "plan.score.range") and issue(text, "plan.next.invalid"), text)


def direction_core(ctx):
    reviews = {key: value for key, value in records(read(ctx, "project/discoveries.md"), "D").items()
               if value.get("Kind") == "direction-review"}
    return result(reviews and all(all(value.get(name, "").strip() for name in ("Gap", "Decisions", "Data audit"))
                                  for value in reviews.values()), reviews)


def review_identity(ctx):
    text = read(ctx, "before.txt")
    return result(all(issue(text, "discovery.review.identity", contains=(key,)) for key in ("D-A-001", "D-A-002")), text)


def missing_cross_check(ctx):
    text = read(ctx, "before.txt")
    missing = [line for line in text.splitlines() if re.match(r"^(?:- )?ERROR discovery.field.missing\b", line)
               and "D-A-003" in line and "Cross-check" in line]
    return result(len(missing) == 1 and not issue(text, "discovery.state.unknown", contains=("D-A-003",)), text)


def pending_records(ctx):
    found = records(read(ctx, "project/discoveries.md"), "D")
    return result(set(found) == {"D-A-001", "D-A-002", "D-A-003"}
                  and all(row.get("Cross-check") == "PENDING" for row in found.values()), found)


EXAMPLES = {"quick-script-cleanup", "work-project-data-migration", "solo-research-literature-replication",
            "team-research-cv-leakage", "competition-solo-tabular", "competition-team-forecasting"}


def example_counts(ctx):
    data = ctx.data("results.json")
    return result(isinstance(data, dict) and set(data) == EXAMPLES
                  and all(isinstance(row, dict) and set(row) == {"ERROR", "WARN", "INFO"}
                          and all(type(value) is int and value == 0 for value in row.values()) for row in data.values()), data)


def example_controls(ctx):
    data = ctx.data("control-records.json")
    expected = {"team-research-cv-leakage": {"D-B-001", "D-A-001", "D-A-002"},
                "competition-solo-tabular": {"D-A-002"}, "competition-team-forecasting": {"D-A-001"}}
    ok = isinstance(data, dict)
    for name, ids in expected.items():
        rows = data.get(name, {})
        ok = ok and isinstance(rows, dict) and set(rows) == ids and all(
            isinstance(value, str) and (re.search(r"selection gain\s+[+-]?\d", value) or
                                        re.match(r"not applicable\s+—\s+\S.+;\s*alternative:\s*\S", value))
            for value in rows.values())
    return result(ok, data)


def example_reports(ctx):
    reports = {path.stem: path.read_text(encoding="utf-8") for path in (ctx.outputs / "checks").iterdir() if path.is_file()}
    return result(set(reports) == EXAMPLES and all(clean_text(text, info=True) for text in reports.values()), reports)


def cadence_settings(ctx):
    details = {}
    for name in ("fresh", "paused", "resumed"):
        settings = fields(read(ctx, f"{name}/agents.md"))
        shared = fields(read(ctx, f"{name}/handoff.md"))
        discoveries = records(read(ctx, f"{name}/discoveries.md"), "D")
        details[name] = {"settings": settings, "applicability": shared.get("Not applicable", ""), "discoveries": discoveries}
        if (not settings.get("Guards", "").startswith("light") or "direction-review=2d" not in settings.get("Guard thresholds", "")
                or re.search(r"(?:^|;)\s*GD\s+—", shared.get("Not applicable", ""))
                or any(row.get("Kind") == "direction-review" for row in discoveries.values())):
            return result(False, details)
    return result(True, details)


def fresh_grace(ctx):
    text = read(ctx, "fresh-check.txt")
    return result(clean_text(text) and issue(text, "guard.direction.stale", "INFO")
                  and re.search(r"first direction review due \d{4}-\d{2}-\d{2}", text), text)


def paused_cadence(ctx):
    text = read(ctx, "paused-check.txt")
    return result(fields(read(ctx, "paused/handoff.md")).get("Paused") == "2020-01-03"
                  and checker_result(text) and not issue(text, "guard.direction.stale"), text)


def project_roots(ctx):
    return sorted({path.parent for path in ctx.outputs.rglob("agents.md")
                   if all((path.parent / name).is_file() for name in ("plan.md", "discoveries.md", "handoff.md"))})


def project_checks(ctx):
    # Cache only within this saved-run context; no project files are mutated by the checker.
    if hasattr(ctx, "_objective_project_checks"):
        return ctx._objective_project_checks
    found = []
    for root in project_roots(ctx):
        run = subprocess.run([ctx.python, str(ctx.checker_skill / "scripts/check_project.py"), str(root)],
                             capture_output=True, text=True, encoding="utf-8", timeout=30,
                             creationflags=helpers().no_window_flags())
        found.append({"root": root.relative_to(ctx.outputs).as_posix(),
                      "settings": fields((root / "agents.md").read_text(encoding="utf-8")),
                      "shared": fields((root / "handoff.md").read_text(encoding="utf-8")),
                      "discoveries": records((root / "discoveries.md").read_text(encoding="utf-8"), "D"),
                      "actions": records((root / "handoff.md").read_text(encoding="utf-8"), "X"),
                      "instruments": records((root / "handoff.md").read_text(encoding="utf-8"), "I"),
                      "output": run.stdout + run.stderr, "code": run.returncode})
    ctx._objective_project_checks = found
    return found


def check_scenarios(selector, check, modes=(), severity=None, absent=False, detail=()):
    def run(ctx):
        selected = [case for case in project_checks(ctx) if selector(case)]
        ok = bool(selected) and all(checker_result(case["output"]) and
                                   ((not issue(case["output"], check)) if absent else
                                    issue(case["output"], check, severity, detail)) for case in selected)
        if modes:
            ok = ok and all(any(case["settings"].get("Guards", "").startswith(mode) for case in selected) for mode in modes)
            if severity is None and not absent:
                ok = ok and all(issue(case["output"], check,
                                      "ERROR" if case["settings"].get("Guards", "").startswith("strict") else "WARN",
                                      detail) for case in selected)
        return result(ok, [{key: value for key, value in case.items() if key in {"root", "output"}} for case in selected])
    return run


def active(case, row, guard):
    settings, shared = case["settings"], case["shared"]
    guards = settings.get("Guards", "off")
    since = re.search(r"since (\d{4}-\d{2}-\d{2})", guards)
    date = row.get("Date") or next(iter(re.findall(r"\d{4}-\d{2}-\d{2}", row.get("Result", ""))), "9999")
    return (guards != "off" and guard in settings.get("Guard set", "")
            and not re.search(rf"(?:^|;)\s*{guard}\s+—", shared.get("Not applicable", ""))
            and not (since and date < since[1]))


def matching(case, field, value, prefix="discoveries", guard="G1"):
    return any(value in row.get(field, "") and active(case, row, guard) for row in case[prefix].values())


def selection_rows(case):
    picks = re.findall(r"\bX-[A-Z]+-\d+\b", case["shared"].get("Final picks", ""))
    return [(key, case["actions"].get(key)) for key in picks]


def same_family(case):
    rows = selection_rows(case)
    return (len(rows) == 2 and all(row and active(case, row, "G11") for _, row in rows)
            and all(row.get("Family") == "parser-a" for _, row in rows))


def control_record(ctx):
    rows = [row for case in project_checks(ctx) for row in case["discoveries"].values()]
    return result(any(re.fullmatch(r"artifacts/placebo\.csv;\s*selection gain 0\.006", row.get("Control", "")) for row in rows), rows)


def json_file(ctx, suffix, action):
    matches = list(ctx.outputs.rglob(f".ro/{suffix}/{action}.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in matches]


def response(action, code, remote, diagnostic):
    def run(ctx):
        rows = json_file(ctx, "external-results", action)
        return result(len(rows) == 1 and rows[0].get("action") == action and rows[0].get("returncode") == code
                      and remote in rows[0].get("stdout", "") and diagnostic in rows[0].get("stderr", ""), rows)
    return run


def logs(ctx, basename):
    return [(path.relative_to(ctx.outputs).as_posix(), path.read_text(encoding="utf-8").splitlines())
            for path in ctx.outputs.rglob(basename)]


def execution_lines(basename, expected):
    def run(ctx):
        values = logs(ctx, basename)
        lines = [line for _, content in values for line in content if line.strip()]
        return result(lines == expected, values)
    return run


def attempt_state(ctx):
    rows = [json.loads(line) for line in read(ctx, "attempt-state.jsonl").splitlines() if line.strip()]
    if len(rows) != 2 or {row.get("action") for row in rows} != {"X-A-001", "X-A-002"}:
        raise ValueError("Expected one captured start-state row per action")
    return rows


def journal_started(ctx):
    rows = attempt_state(ctx)
    return result(all(row.get("status_at_start") == "in-flight" for row in rows), rows)


def journal_key(ctx):
    rows = attempt_state(ctx)
    return result(all(isinstance(row.get("journal_key"), str) and row["journal_key"]
                      and row["journal_key"] == row.get("child_key") for row in rows), rows)


def journal_deadline(ctx):
    rows = attempt_state(ctx)
    return result(all(type(row.get("deadline_seconds")) in {float, int} and math.isfinite(row["deadline_seconds"])
                      and row["deadline_seconds"] > 0 for row in rows), rows)


def terminal_statuses(ctx):
    rows = records(read(ctx, "handoff.md"), "X")
    return result(rows.get("X-A-001", {}).get("Status") == "done" and rows.get("X-A-002", {}).get("Status") == "error", rows)


def reconciliation_report(ctx):
    text = read(ctx, "reconciliation.md")
    table = {}
    table_lines = [line for line in text.splitlines() if line.strip().startswith("|")]
    if table_lines:
        headers = [cell.strip().lower() for cell in table_lines[0].strip().strip("|").split("|")]
        for line in table_lines[1:]:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == len(headers):
                row = dict(zip(headers, cells))
                action = next((cell for cell in cells if re.fullmatch(r"X-A-00[12]", cell)), None)
                if action:
                    table[action] = row
    groups = {}
    for action, remote, code, diagnostic in (("X-A-001", "archive-accepted-482", 0, "receipt stored"),
                                            ("X-A-002", "archive-uncertain-731", 7, "acknowledgement lost")):
        pieces = [part for part in re.split(r"\n\s*\n|^#{1,6} ", text, flags=re.M) if action in part]
        groups[action] = [part for part in pieces if remote in part and diagnostic in part
                          and re.search(rf"(?:exit(?: code)?|returncode|code)\D{{0,12}}{code}\b", part, re.I)]
        row = table.get(action, {})
        codes = [value for key, value in row.items() if re.search(r"exit|return|code", key)]
        if str(code) in codes and remote in " ".join(row.values()) and diagnostic in " ".join(row.values()):
            groups[action].append(" ".join(row.values()))
    uncertainty = [part for part in groups["X-A-002"] if re.search(r"reconcil\w*.*(?:before|prior).*retry|retry.*after.*reconcil", part, re.I)]
    return result(all(groups.values()) and uncertainty, groups)


def unchanged_ledger(ctx):
    original = (ctx.case_dir / "files/handoff.md").read_bytes()
    return result((ctx.outputs / "handoff.md").read_bytes() == original, "Exact handoff.md bytes compared")


def duplicate_status(ctx):
    text = read(ctx, "validation-report.md")
    lines = [line for line in text.splitlines() if "X-A-001" in line and re.search(r"duplicate.*Status|Status.*duplicate", line, re.I)]
    return result(len(lines) >= 2, lines)


def no_mock(ctx):
    values = logs(ctx, "executions.log")
    commands = [entry.get("command", "") for entry in ctx.executions]
    bypass = [command for command in commands if re.search(r"python[^\n]*\s+mock_archive\.py", command)
              and not re.search(r"\bexternal\b[^\n]*\s--\s", command)]
    return result(not values and not bypass, {"execution_logs": values, "direct_commands": bypass})


def unknown_attempt(ctx):
    rows = records(read(ctx, "handoff.md"), "X")
    attempts = json_file(ctx, "external-attempts", "X-A-001")
    return result(rows.get("X-A-001", {}).get("Status") == "unknown" and len(attempts) == 1
                  and attempts[0].get("status") == "unknown", {"ledger": rows, "attempts": attempts})


def stable_retry_key(ctx):
    rows = [row for action in ("X-A-001", "X-A-002", "X-A-003")
            for row in json_file(ctx, "external-attempts", action)]
    keys = {row.get("idempotency_key") for row in rows}
    return result(len(rows) == 3 and len(keys) == 1 and isinstance(next(iter(keys)), str) and next(iter(keys)), rows)


def reconciled_chain(ctx):
    candidates = []
    for path in ctx.outputs.rglob("handoff.md"):
        rows = records(path.read_text(encoding="utf-8"), "X")
        if set(rows) >= {"X-A-001", "X-A-002", "X-A-003"} and rows["X-A-003"].get("Status") == "done":
            candidates.append(rows)
    valid = False
    for rows in candidates:
        valid = True
        for key, next_key in (("X-A-001", "X-A-002"), ("X-A-002", "X-A-003")):
            row, following = rows[key], rows[next_key]
            match = re.fullmatch(r"not-accepted \(observed (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\);\s*(\S.+)", row.get("Reconciled", ""))
            times = [datetime.fromisoformat(value) for name in ("Expected", "Result")
                     for value in re.findall(r"(?:written|observed) (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", row.get(name, ""))]
            next_times = re.findall(r"written (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", following.get("Expected", ""))
            if not (match and len(times) == 2 and len(next_times) == 1 and following.get("Retry of") == key
                    and max(times) <= datetime.fromisoformat(match[1]) < datetime.fromisoformat(next_times[0])):
                valid = False
        if valid:
            break
    return result(valid, candidates)


def saved_reports(ctx):
    return [(path.relative_to(ctx.outputs).as_posix(), path.read_text(encoding="utf-8"))
            for path in ctx.outputs.rglob("*") if path.is_file() and path.suffix in {".txt", ".md", ".log"}
            and path.name not in {"agents.md", "plan.md", "discoveries.md", "handoff.md"}]


def recorded_issue(check, severity):
    def run(ctx):
        reports = [(path, text) for path, text in saved_reports(ctx) if issue(text, check, severity)]
        return result(bool(reports), reports)
    return run


def measurement_dangling(ctx):
    outputs = project_checks(ctx)
    groups = {kind: [case for case in outputs if matching(case, "Result", "I-A-99", kind, "G3")]
              for kind in ("discoveries", "actions")}
    return result(all(cases and all(issue(case["output"], "evidence.instrument.dangling", "ERROR", ("I-A-99",))
                                   for case in cases) for cases in groups.values()), groups)


def dangling_exemptions(ctx):
    variants = {"historical": [], "off": [], "inapplicable": []}
    for case in project_checks(ctx):
        citing = [row for row in [*case["discoveries"].values(), *case["actions"].values()]
                  if "I-A-99" in " ".join(row.get(key, "") for key in ("Instrument", "Result", "Rejected on"))]
        if not citing:
            continue
        if case["settings"].get("Guards") == "off":
            variants["off"].append(case)
        elif re.search(r"(?:^|;)\s*G[135]\s+—\s+\S", case["shared"].get("Not applicable", "")):
            variants["inapplicable"].append(case)
        else:
            since = re.search(r"since (\d{4}-\d{2}-\d{2})", case["settings"].get("Guards", ""))
            if since and all(row.get("Date", "9999") < since[1] for row in citing):
                variants["historical"].append(case)
    return result(all(group and all(not issue(case["output"], "evidence.instrument.dangling") for case in group)
                      for group in variants.values()), variants)


def localized_rejection(ctx):
    outputs = project_checks(ctx)
    selected = {}
    for language, pattern in (("ko", r"[가-힣]"), ("ja", r"[ぁ-ヿ]"), ("en", r"The proposed change failed")):
        for mode, severity in (("light", "WARN"), ("strict", "ERROR")):
            cases = [case for case in outputs if case["settings"].get("Guards", "").startswith(mode)
                     and any(re.search(pattern, row.get("Finding", "")) and row.get("Outcome") == "rejected"
                             and "Rejected on" not in row and active(case, row, "G5") for row in case["discoveries"].values())]
            selected[language + "/" + mode] = cases
            if not cases or not all(issue(case["output"], "guard.rejection.evidence", severity) for case in cases):
                return result(False, selected)
    report = read(ctx, "results.md")
    return result("guard.rejection.evidence" in report and "WARN" in report and "ERROR" in report, selected)


def valid_selections(ctx):
    groups = {"diverse": [], "rationale": []}
    for case in project_checks(ctx):
        rows = selection_rows(case)
        if len(rows) != 2 or not all(row and active(case, row, "G11") and row.get("Family") for _, row in rows):
            continue
        if len({row["Family"] for _, row in rows}) == 2:
            groups["diverse"].append(case)
        elif re.search(r"rationale:\s*\S.+", case["shared"].get("Final picks", "")):
            groups["rationale"].append(case)
    return result(all(group and all(not issue(case["output"], "guard.selection.rationale") for case in group)
                      for group in groups.values()), groups)


def selection_exemptions(ctx):
    groups = {"historical": [], "inapplicable": []}
    for case in project_checks(ctx):
        rows = selection_rows(case)
        if not rows:
            continue
        if re.search(r"(?:^|;)\s*G11\s+—\s+\S", case["shared"].get("Not applicable", "")):
            groups["inapplicable"].append(case)
        elif all(row and not active(case, row, "G11") for _, row in rows) and case["settings"].get("Guards") != "off":
            groups["historical"].append(case)
    return result(all(group and all(not issue(case["output"], "guard.selection.rationale") and
                                    not issue(case["output"], "guard.selection.family") for case in group)
                      for group in groups.values()), groups)


def descendant_report(ctx, delayed=False):
    report = ctx.data("descendant-report.json")
    # The task does not fix JSON keys. Accept clear synonymous observation labels,
    # but require typed values and corroborating retained process/journal artifacts.
    def leaves(value, prefix=""):
        if isinstance(value, dict):
            return [leaf for key, item in value.items() for leaf in leaves(item, f"{prefix}/{key}")]
        return [(prefix, value)]
    flat = leaves(report)
    alive = [value for key, value in flat if re.search(r"(?:grandchild|descendant|pid|process).*alive|alive.*(?:grandchild|descendant|pid|process)", key, re.I)]
    elapsed = [value for key, value in flat if re.search(r"elapsed|waited|seconds_since", key, re.I)
               and type(value) in {int, float}]
    pids = list(ctx.outputs.rglob("grandchild.pid"))
    journal = json_file(ctx, "external-attempts", "X-A-001")
    commands = [entry.get("command", "") for entry in ctx.executions]
    manual = any(re.search(r"\b(?:kill|taskkill|Stop-Process)\b", command, re.I) for command in commands)
    if delayed:
        ok = not list(ctx.outputs.rglob("late-effect.txt")) and elapsed and max(elapsed) >= 4
    else:
        ok = len(pids) == 1 and pids[0].read_text(encoding="utf-8").strip().isdigit() and alive and all(value is False for value in alive) and not manual
    return result(ok and len(journal) == 1 and journal[0].get("status") == "unknown", report)


def refused_retry(ctx, action, basename, expected):
    okay, log = execution_lines(basename, expected)(ctx)
    reports = saved_reports(ctx)
    refused = [(path, text) for path, text in reports if action in text and
               re.search(r"already attempted|already.*(?:done|complete)|not prepared|replay.*refus|refus.*replay|reconcile before", text, re.I)]
    return result(okay and refused, {"logs": log, "refusals": refused})


def retry_chain_clean(ctx):
    selected = [case for case in project_checks(ctx) if case["actions"].get("X-A-003", {}).get("Status") == "done"
                and case["actions"].get("X-A-002", {}).get("Retry of") == "X-A-001"
                and case["actions"].get("X-A-003", {}).get("Retry of") == "X-A-002"]
    return result(selected and all(not issue(case["output"], "external.retry.invalid") and not issue(case["output"], "ext.duplicate")
                                    for case in selected), selected)


def retry_defects(text):
    rows = records(text, "X")
    defects = set()
    ids = re.findall(r"^### (X-[A-Z]+-\d+)\b", text, re.M)
    if len(ids) != len(set(ids)):
        defects.add("ambiguous")
    for key, row in rows.items():
        previous = row.get("Retry of")
        if previous:
            if previous not in rows:
                defects.add("missing")
            elif previous == key:
                defects.add("self")
            else:
                prior = rows[previous]
                stamps = lambda r: re.findall(r"written (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", r.get("Expected", ""))
                if stamps(row) and stamps(prior) and stamps(prior)[0] >= stamps(row)[0]:
                    defects.add("forward")
                if any(row.get(name, "").strip() != prior.get(name, "").strip() for name in ("Candidate", "Destination")):
                    defects.add("mismatched")
                if prior.get("Retry of") and prior["Retry of"] not in rows:
                    defects.add("ancestor")
            visited = {key}
            while previous in rows:
                if previous in visited:
                    defects.add("cyclic")
                    break
                visited.add(previous)
                previous = rows[previous].get("Retry of")
        if row.get("Status") == "prepared":
            for other_key, other in rows.items():
                if key == other_key or any(row.get(name, "").strip() != other.get(name, "").strip()
                                           for name in ("Candidate", "Destination")):
                    continue
                if other.get("Status") == "done":
                    defects.add("earlier")
                if "Retry of" not in row and re.search(r"^- Candidate:.*[ \t]+$", text, re.M):
                    defects.add("padded")
    return defects


def refusal_scenarios(labels, reason, checker=None):
    """Bind structurally identified bad ledgers to rejection evidence and no effects."""
    def run(ctx):
        evidence = []
        for label in labels:
            matches = []
            for path in ctx.outputs.rglob("handoff.md"):
                folder = path.parent
                relative = folder.relative_to(ctx.outputs).as_posix()
                ledger = path.read_text(encoding="utf-8")
                if label not in retry_defects(ledger):
                    continue
                text = "\n".join(p.read_text(encoding="utf-8") for p in folder.glob("*")
                                  if p.is_file() and p.suffix in {".txt", ".log", ".md"} and p.name != "handoff.md")
                attempts = folder / "attempts.log"
                prepared = {key for key, row in records(ledger, "X").items() if row.get("Status") == "prepared"}
                logged = set(attempts.read_text(encoding="utf-8").splitlines()) if attempts.exists() else set()
                no_effect = bool(prepared) and not (prepared & logged)
                matching_error = re.search(reason, text, re.I)
                if no_effect and matching_error and (not checker or issue(text, checker)):
                    matches.append(relative)
            evidence.append({"scenario": label, "matching_saved_refusals": matches})
        return result(all(row["matching_saved_refusals"] for row in evidence), evidence)
    return run


def command_results(ctx):
    """All completed commands, including denied nonzero calls excluded by executions."""
    rows = []
    path = ctx.run_dir / "events.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item", {})
        if not isinstance(item, dict):
            continue
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            rows.append(item)
    return rows


def command_failure(ctx, folder, flag, diagnostic):
    matches = []
    for entry in command_results(ctx):
        command, output = entry.get("command", ""), entry.get("aggregated_output", "")
        nonzero = (type(entry.get("exit_code")) is int and entry["exit_code"] != 0) or re.search(
            r"(?:returncode|exit.code)\s*[:=]\s*[1-9]\d*", output, re.I)
        if ("init_research_orchestrator.py" in command and folder in command and re.search(flag, command)
                and nonzero and re.search(diagnostic, output, re.I)):
            matches.append({"command": command, "exit_code": entry.get("exit_code"), "output": output})
    return result(bool(matches), matches)


def all_texts(ctx):
    collected = []
    for path in ctx.outputs.rglob("*"):
        if path.is_file() and (path.suffix in {".md", ".txt", ".log"} or "agents.md" in path.name):
            try:
                collected.append((path, path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    return collected


def settings_snapshots(ctx):
    return [(path, text, fields(text)) for path, text in all_texts(ctx) if "## Project settings" in text]


def setting_project(ctx, name):
    matches = [case for case in project_roots(ctx) if case.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one retained {name} project, got {len(matches)}")
    return matches[0]


def simple_shape(ctx):
    text = read(ctx, "project/plan.md")
    items = records(text, "H")
    forbidden = {"Resource", "Parallel", "Other", "Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"}
    return result(len(items) == 1 and all(row.get("Goal") and row.get("Evidence") and
                                        (row.get("Next test") or row.get("Next step")) and not forbidden.intersection(row)
                                        for row in items.values()), items)


def goal_search(ctx):
    items = records(read(ctx, "project/plan.md"), "H")
    report = read(ctx, "duplicate-check.txt")
    return result(any("amber-crate" in row.get("Goal", "") and key in report and "amber-crate" in report
                      for key, row in items.items()), {"items": items, "search": report})


def host_default(ctx):
    selected = fields(read(ctx, "project/agents.md")).get("Platforms")
    attempts = [row for row in command_results(ctx) if "init_research_orchestrator.py" in row.get("command", "")
                and "--platforms" not in row.get("command", "") and row.get("exit_code") == 0]
    return result(selected and any(re.search(r"(?:detected|default|local|Platforms)", row.get("aggregated_output", ""), re.I)
                                  and selected in row.get("aggregated_output", "") for row in attempts), attempts)


def inactive_pointers(ctx):
    text = read(ctx, "project/agents.md")
    return result(all(name not in text for name in ("plan-collector.md", "external-actions.md", "compute.md")), text)


def pointers(ctx, enabled=None, omitted=(), core=False, custom=False):
    snapshots = settings_snapshots(ctx)
    eligible = [(path, text, setting) for path, text, setting in snapshots if
                setting.get("Preset") == ("custom" if custom else "quick") and
                (enabled is None or (setting.get("Plan collector", "off") != "off") == enabled)]
    valid = []
    for path, text, setting in eligible:
        generated = text.split("## Project rules", 1)[0]
        okay = all(name not in generated for name in omitted)
        if enabled is True:
            okay = okay and "plan-collector.md" in generated
        elif enabled is False:
            okay = okay and "plan-collector.md" not in generated
        if core:
            okay = okay and bool(re.search(r"SKILL\.md#|core.*operation|operation.*core", generated, re.I))
        if custom:
            okay = okay and not re.search(r"\n{3,}", generated.replace("\r\n", "\n"))
        if okay:
            valid.append(path.relative_to(ctx.outputs).as_posix())
    return result(bool(valid), {"matching_snapshots": valid})


def transition_setting(name, expected=None, nonempty=False, block=False):
    def run(ctx):
        root = setting_project(ctx, name)
        setting = fields((root / "agents.md").read_text(encoding="utf-8"))
        value = setting.get("External actions", "")
        okay = value == expected if expected is not None else bool(value and value != "none") if nonempty else True
        if block:
            okay = okay and "external.gate" in setting.get("Block", "").split(", ")
        return result(okay, setting)
    return run


def inactive_transition(name):
    def run(ctx):
        okay, settings = transition_setting(name, "none")(ctx)
        rows = [entry for entry in command_results(ctx) if "init_research_orchestrator.py" in entry.get("command", "")
                and name in entry.get("command", "") and re.search(r"external.*(?:inactive|not active)", entry.get("aggregated_output", ""), re.I)
                and re.search(r"(?:External actions|command patterns)", entry.get("aggregated_output", ""), re.I)]
        return result(okay and rows, {"settings": settings, "initializer_results": rows})
    return run


def hook_results(ctx):
    rows = []
    for path in ctx.outputs.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        entries = value if isinstance(value, list) else [value]
        for row in entries:
            if isinstance(row, dict) and ("hookSpecificOutput" in row or "decision" in row or "permissionDecision" in row):
                rows.append((path.relative_to(ctx.outputs).as_posix(), row))
    return rows


def transition_hooks(ctx, deny=True):
    cases = ("inherited", "custom") if deny else ("opted-out",)
    matched = {}
    for case in cases:
        matched[case] = []
        for name, row in hook_results(ctx):
            if case not in name:
                continue
            detail = row.get("hookSpecificOutput", row)
            denial = detail.get("permissionDecision") == "deny" or row.get("decision") in {"block", "deny"}
            reason = str(detail.get("permissionDecisionReason", row.get("reason", "")))
            matches = (denial and "external.gate" in reason) if deny else (not denial or "external.gate" not in reason)
            if matches:
                matched[case].append(row)
    direct = [entry.get("command", "") for entry in command_results(ctx)
              if re.search(r"(?:^|[;&])\s*(?:kaggle competitions submit|release-client publish)\b", entry.get("command", ""))]
    return result(all(matched.values()) and not direct, {"hooks": matched, "direct_outward_calls": direct})


def freeze_delivery(ctx):
    items = records(read(ctx, "plan.md"), "H")
    return result(any(row.get("Ready by") == "2099-01-02" and "archive" in row.get("Goal", row.get("Hypothesis", "")).lower()
                      for row in items.values()), items)


def freeze_scope(ctx):
    items = records(read(ctx, "plan.md"), "H")
    outcomes = read(ctx, "handoff.md") + "\n" + read(ctx, "discoveries.md")
    return result(len(items) == 1 and any("archive" in row.get("Goal", row.get("Hypothesis", "")).lower() for row in items.values())
                  and "packaging" in outcomes.lower() and "packaging" not in read(ctx, "plan.md").lower(),
                  {"items": items, "outcomes": outcomes})


def freeze_expiry(ctx):
    report = read(ctx, "checks.md")
    # Date-bearing report sections bind the diagnostic to its simulated clock.
    sections = [part for part in re.split(r"(?m)(?=^#{1,6} .*(?:2099-01-01|2099-01-02))", report) if part.strip()]
    earlier = [part for part in sections if "2099-01-01" in part.splitlines()[0] and re.search(r"12:00|noon", part, re.I)]
    later = [part for part in sections if "2099-01-02" in part.splitlines()[0] and re.search(r"12:00|noon", part, re.I)]
    executed = [entry for entry in command_results(ctx) if re.search(r"check_project|Checker\(", entry.get("command", ""))
                and re.search(r"2099.*(?:1, *1|01-01)|2099.*(?:1, *2|01-02)", entry.get("command", ""))]
    return result(earlier and later and executed and all(not issue(part, "plan.freeze.expired") for part in earlier)
                  and all(issue(part, "plan.freeze.expired", "WARN") for part in later), report)


def manifest(value):
    if isinstance(value, dict) and isinstance(value.get("files"), (dict, list)):
        value = value["files"]
    if isinstance(value, list):
        value = {row.get("path", row.get("name")): row.get("sha256", row.get("hash")) for row in value if isinstance(row, dict)}
    if not isinstance(value, dict):
        return {}
    rows = {str(key).replace("\\", "/"): val.get("sha256", val.get("hash")) if isinstance(val, dict) else val for key, val in value.items()}
    return {key: val for key, val in rows.items() if isinstance(val, str) and re.fullmatch(r"[0-9a-f]{64}", val)}


def snapshot_preservation(ctx, complete=False):
    before, after = manifest(ctx.data("before.json")), manifest(ctx.data("after.json"))
    if complete:
        actual = {path.relative_to(ctx.outputs / "trial").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (ctx.outputs / "trial").rglob("*") if path.is_file()}
        required = {"nested/archive.txt", "notes.txt", ".ro/local-state.json", "agents.md", "discoveries.md", "handoff.md"}
        okay = before == after == actual and required <= actual.keys()
    else:
        okay = before and before == after
    return result(okay, {"before": before, "after": after})


def snapshot_refusal(ctx):
    okay, evidence = command_failure(ctx, "trial", r"--workflow[ =]+[\"']?unified", r"(?:stored|existing).*workflow|workflow.*(?:conflict|classic)")
    return result(okay and not (ctx.outputs / "trial/plan.md").exists(), evidence)


def comparison_controls(ctx):
    code = [path for path in ctx.outputs.glob("*.py") if re.search(r"before|manifest", path.read_text(encoding="utf-8"))
            and re.search(r"after|compare", path.read_text(encoding="utf-8"))]
    rows = [entry for entry in command_results(ctx) if any(path.name in entry.get("command", "") for path in code)]
    output = "\n".join(entry.get("aggregated_output", "") for entry in rows)
    return result(code and re.search(r"(?:unchanged|unmodified|equal).*?(?:True|PASS|equal)", output, re.I)
                  and re.search(r"(?:hash|changed).*?(?:False|mismatch|PASS)", output, re.I)
                  and re.search(r"(?:extra|added).*?(?:False|mismatch|PASS)", output, re.I), output)


def repaired_layout(ctx):
    classic = read(ctx, "archive-a/plan.md")
    unified = read(ctx, "intake-b/plan.md")
    return result("## Agent:" in classic and "## Queue" not in classic and "## Queue" in unified and "## Agent:" not in unified,
                  {"classic": classic, "unified": unified})


def repaired_names(ctx):
    return result("Archive review" in read(ctx, "archive-a/plan.md") and "Intake review" in read(ctx, "intake-b/handoff.md"),
                  "Stored names checked in regenerated files")


def repaired_roster(ctx):
    text = read(ctx, "archive-a/plan.md")
    return result(set(re.findall(r"^## Agent: (\S+)$", text, re.M)) == {"B", "AA"}, text)


def repaired_users(ctx):
    users = fields(read(ctx, "archive-a/handoff.md")).get("Users", "")
    return result(set(re.split(r"\s*,\s*", users)) >= {"lee", "kim"}, users)


def repaired_clean(ctx):
    runs = project_checks(ctx)
    expected = {"archive-a", "intake-b", "settings-c"}
    selected = [case for case in runs if case["root"].split("/")[-1] in expected]
    return result({case["root"].split("/")[-1] for case in selected} == expected
                  and all(clean_text(case["output"]) for case in selected), selected)


def repair_survivors(ctx, rules_only=False):
    evidence = []
    targets = ("intake-b",) if rules_only else ("archive-a", "intake-b")
    for name in targets:
        folder = ctx.outputs / name
        files = ("agents.md",) if rules_only else tuple(file for file in ("agents.md", "plan.md", "discoveries.md", "handoff.md")
                                                      if file != {"archive-a": "plan.md", "intake-b": "handoff.md"}[name])
        for file in files:
            current = (folder / file).read_bytes()
            candidates = [path for path in ctx.outputs.rglob("*") if path.is_file() and path != folder / file
                          and name in path.as_posix() and (file in path.name or path.name == file)
                          and any(part in path.as_posix().lower() for part in ("before", "original", "saved", "backup", "after", "repaired"))]
            if rules_only:
                marker = b"## Project rules"
                actual = current[current.index(marker):] if marker in current else b""
                matched = [path for path in candidates if marker in path.read_bytes()
                           and path.read_bytes()[path.read_bytes().index(marker):] == actual]
                okay = bool(matched and b"\r\n" in actual and re.search(rb"(?<!\r)\n", actual)
                            and re.search(rb" +\r?\n", actual) and not actual.endswith(b"\n"))
            elif name == "intake-b" and file == "agents.md":
                # The later language edit is authorized; require a separate after-repair
                # snapshot equal to the original so it cannot hide a repair-time mutation.
                after_repair = [path for path in candidates if re.search(r"after.?repair|repaired", path.as_posix(), re.I)]
                before_repair = [path for path in candidates if path not in after_repair]
                matched = [path for path in before_repair if path.read_bytes() == current or
                           any(path.read_bytes() == after.read_bytes() for after in after_repair)]
                okay = bool(matched and b"Preserve the original source archive." in current)
            else:
                matched = [path for path in candidates if path.read_bytes() == current]
                okay = bool(matched and (file != "agents.md" or b"Preserve the original source archive." in current))
            evidence.append({"project": name, "file": file, "preserved": okay})
    return result(all(row["preserved"] for row in evidence), evidence)


def stored_manifests(ctx):
    found = []
    for path in ctx.outputs.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        parsed = manifest(value)
        if parsed:
            found.append((path.relative_to(ctx.outputs).as_posix(), parsed))
    return found


def refused_repair_snapshots(ctx):
    manifests = stored_manifests(ctx)
    evidence = {}
    for trial, missing in (("archive-a", "plan.md"), ("intake-b", "handoff.md")):
        before = [(name, rows) for name, rows in manifests if trial in name and re.search(r"before|pre-", name, re.I)]
        after = [(name, rows) for name, rows in manifests if trial in name and re.search(r"after|post-", name, re.I)]
        pairs = [(name, other) for name, rows in before for other, updated in after if rows == updated
                 and missing not in {key.rsplit("/", 1)[-1] for key in rows}
                 and len(rows) >= 3]
        evidence[trial] = pairs
    return result(all(evidence.values()), evidence)


def repair_conflicts(ctx):
    checks = [command_failure(ctx, "archive-a", r"--workflow[ =]+[\"']?unified", r"workflow|migrat"),
              command_failure(ctx, "intake-b", r"--verification[ =]+[\"']?self", r"verification|reconfigur")]
    snapshots, details = refused_repair_snapshots(ctx)
    return result(all(okay for okay, _ in checks) and snapshots, {"refusals": checks, "snapshots": details})


def snapshot_boundary(ctx):
    commands = command_results(ctx)
    candidates = []
    for index, row in enumerate(commands):
        command = row.get("command", "")
        if "init_research_orchestrator.py" not in command or "--workflow" not in command or "unified" not in command:
            continue
        before = commands[max(0, index - 1)].get("command", "")
        after = commands[min(len(commands) - 1, index + 1)].get("command", "")
        # Accept one script that takes the two snapshots around the subprocess call,
        # or adjacent tool calls with no intervening project mutation.
        inline = re.search(r"before\.json.*init_research_orchestrator\.py.*after\.json", command, re.S)
        adjacent = "before.json" in before and "after.json" in after
        if inline or adjacent:
            candidates.append(index)
    forbidden = [path.relative_to(ctx.outputs / "trial").as_posix() for path in (ctx.outputs / "trial").rglob("*")
                 if path.is_file() and (path.name in {"before.json", "after.json"} or
                                       re.search(r"(?:report|compare|snapshot|command).*\.(?:md|py|log|txt)$", path.name, re.I))]
    return result(candidates and not forbidden, {"snapshot_command_positions": candidates, "misplaced_evidence": forbidden})


def compact_reconfigure(ctx):
    # Saved text snapshots and command-result hashes are both acceptable evidence.
    snapshots = [(path, path.read_bytes()) for path, _, setting in settings_snapshots(ctx) if setting.get("Git sync") == "commit"]
    identical = [(a.relative_to(ctx.outputs).as_posix(), b.relative_to(ctx.outputs).as_posix())
                 for index, (a, first) in enumerate(snapshots) for b, second in snapshots[index + 1:] if first == second]
    commands = [row for row in command_results(ctx) if "--reconfigure" in row.get("command", "")]
    hashes = []
    for entry in commands:
        hashes.extend(re.findall(r"\b[0-9a-fA-F]{64}\b", entry.get("aggregated_output", "")))
    reconfigure_count = sum(len(re.findall(r"--reconfigure\b", row.get("command", ""))) for row in commands)
    return result(reconfigure_count >= 2 and (identical or any(hashes.count(value) >= 2 for value in set(hashes))),
                  {"identical_snapshots": identical, "reconfigure_commands": len(commands), "hashes": hashes})


def free_slot_refusal(ctx):
    text = read(ctx, "report.md")
    observations = [row for row in command_results(ctx) if re.search(r"\blaunch\b", row.get("command", ""))
                    and re.search(r"(?:slot A|released|Current user|take.*slot)", row.get("aggregated_output", ""), re.I)
                    and re.search(r"(?:refus|error|requires|must|owner)", row.get("aggregated_output", ""), re.I)]
    return result(observations and re.search(r"released", text, re.I) and re.search(r"(?:Current user|user).*none", text, re.I),
                  {"report": text, "observed_refusals": observations})


def free_slot_no_start(ctx):
    rows = command_results(ctx)
    first_launch = next((index for index, row in enumerate(rows) if " launched; confirmed alive" in row.get("aggregated_output", "")), len(rows))
    evidence = []
    for row in rows[:first_launch]:
        command, output = row.get("command", ""), row.get("aggregated_output", "")
        if "worker-started" in command and re.search(r"False|false|absent|not found|does not exist", output):
            evidence.append(row)
    return result(evidence and free_slot_refusal(ctx)[0], evidence)


def free_slot_no_reservation(ctx):
    saved = [(path.relative_to(ctx.outputs).as_posix(), json.loads(path.read_text(encoding="utf-8")))
             for path in ctx.outputs.rglob("*.json") if "job" in path.name and any(
                 key in path.as_posix().lower() for key in ("refus", "before", "released"))]
    empty = [(path, value) for path, value in saved if value == [] or value == {"jobs": []}]
    rows = command_results(ctx)
    first_launch = next((index for index, row in enumerate(rows) if " launched; confirmed alive" in row.get("aggregated_output", "")), len(rows))
    observations = [row for row in rows[:first_launch] if "jobs.json" in row.get("command", "")
                    and re.search(r"(?m)^\s*(?:\[\s*\]|\{\s*\"jobs\"\s*:\s*\[\s*\]\s*\})\s*$", row.get("aggregated_output", ""))]
    return result((empty or observations) and free_slot_refusal(ctx)[0], {"empty_registry_snapshots": empty, "observations": observations})


def event_items(ctx):
    data = [json.loads(line) for line in (ctx.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [entry.get("item", {}) for entry in data if isinstance(entry, dict) and isinstance(entry.get("item", {}), dict)]


def reviewer_read_only(ctx):
    expected = {path.relative_to(ctx.case_dir / "files").as_posix(): path.read_bytes()
                for path in (ctx.case_dir / "files").rglob("*") if path.is_file()}
    actual = {path.relative_to(ctx.outputs).as_posix(): path.read_bytes()
              for path in ctx.outputs.rglob("*") if path.is_file() and path.name != "final.md"}
    # final.md is the harness capture of the final response, not a project mutation.
    preserved = expected == actual
    items = event_items(ctx)
    commands = command_results(ctx)
    allowed = {"get-content", "select-string", "get-childitem", "get-item", "resolve-path", "test-path",
               "select-object", "format-list", "format-table", "out-string", "cat", "head", "tail", "sed",
               "rg", "grep", "ls", "find", "pwd", "wc", "nl", "more", "type"}
    dangerous = r"(?:^|[;&|\n])\s*(?:python|python3|py|node|bash|sh|cmd|pwsh|powershell|ro)\b|\b(?:Set-Content|Add-Content|Out-File|Remove-Item|New-Item|WriteAll|write_text|write_bytes|check_project\.py)\b|(?:^|[^<])>>?"
    valid_commands = True
    inspected = False
    for row in commands:
        command = row.get("command", "")
        if __package__:
            from .command_trace import _source
        else:
            from command_trace import _source
        source = _source(command)
        if re.search(dangerous, source, re.I):
            valid_commands = False
            break
        statements = [part.strip() for part in re.split(r"[;|\n]+", source) if part.strip()]
        for statement in statements:
            try:
                words = shlex.split(statement, posix=False)
            except ValueError:
                valid_commands = False
                break
            verb = words[0].strip("\"'").lower() if words else ""
            if verb not in allowed:
                valid_commands = False
                break
            inspected = True
    other_tools = [row for row in items if row.get("type") in {"mcp_tool_call", "tool_call", "function_call"}]
    for row in other_tools:
        name = str(row.get("tool", row.get("name", ""))).lower()
        if not any(token in name for token in ("read", "glob", "grep", "exec_command")):
            valid_commands = False
        else:
            inspected = True
    no_edits = not any(row.get("type") in {"file_change", "patch"} for row in items)
    return result(preserved and inspected and valid_commands and no_edits,
                  {"fixture_bytes_preserved": preserved, "read_only_commands": valid_commands, "no_edit_events": no_edits})


def no_unavailable_review(ctx):
    rows = event_items(ctx)
    forbidden = []
    for row in rows:
        kind = row.get("type", "")
        if "collab" in kind or kind in {"agent_spawn", "agent_wait"}:
            forbidden.append(kind)
        if kind in {"mcp_tool_call", "tool_call", "function_call"}:
            name = str(row.get("name", row.get("tool", "")))
            if re.search(r"spawn_agent|wait_agent|followup_task|send_message.*review|subagent", name, re.I):
                forbidden.append(name)
    for row in command_results(ctx):
        command = row.get("command", "")
        if re.search(r"(?:codex\s+exec|claude\s+-p|spawn_agent|wait_agent|reviewer.*(?:poll|sleep)|(?:poll|sleep).*reviewer)", command, re.I):
            forbidden.append(command)
    final = (ctx.outputs / "final.md").read_text(encoding="utf-8") if (ctx.outputs / "final.md").is_file() else ""
    return result(rows and final.strip() and not forbidden, {"finished_response": bool(final.strip()), "review_session_operations": forbidden})


CHECKS = {
    ("milestone-state-validation", "01-malformed.md"): check_report("before.txt", "guard.phase.state"),
    ("milestone-state-validation", "02-unfinished.md"): milestone_unfinished,
    ("milestone-state-validation", "03-complete.md"): milestone_complete,
    ("work-migration-scheduling", "01-order.md"): migration_order,
    ("work-migration-scheduling", "02-next.md"): migration_next,
    ("work-migration-scheduling", "03-valid.md"): check_report("checker.txt", clean=True),
    ("queue-ordering-validation", "01-lean.md"): lean_queue,
    ("queue-ordering-validation", "02-clean.md"): check_report("clean.txt", clean=True),
    ("queue-ordering-validation", "03-invalid.md"): invalid_queue,
    ("research-direction-scope", "01-core.md"): direction_core,
    ("research-direction-scope", "02-advice.md"): check_report("research.txt", "guard.direction.advice", "INFO", ("guard.direction.incomplete",)),
    ("research-direction-scope", "03-full.md"): check_report("full.txt", "guard.direction.incomplete", "ERROR"),
    ("reviewer-identity-validation", "01-identity.md"): review_identity,
    ("reviewer-identity-validation", "02-missing.md"): missing_cross_check,
    ("reviewer-identity-validation", "03-pending.md"): pending_records,
    ("shipped-example-health", "01-all.md"): example_counts,
    ("shipped-example-health", "02-controls.md"): example_controls,
    ("shipped-example-health", "03-outputs.md"): example_reports,
    ("direction-review-grace", "90-fresh-grace.md"): fresh_grace,
    ("direction-review-grace", "90-guards-retained.md"): cadence_settings,
    ("direction-review-grace", "90-paused-cadence.md"): paused_cadence,
    ("direction-review-grace", "90-resumed-due.md"): check_report("resumed-check.txt", "guard.direction.stale", "INFO"),
    ("control-noise-floor", "90-01-result.md"): control_record,
    ("control-noise-floor", "90-04-result.md"): check_scenarios(lambda c: any("selection gain 0.006" in d.get("Control", "") for d in c["discoveries"].values()), "guard.control.missing", absent=True),
    ("external-result-reconciliation", "90-success-response.md"): response("X-A-001", 0, "archive-accepted-482", "receipt stored; response complete"),
    ("external-result-reconciliation", "90-91-failure-response.md"): response("X-A-002", 7, "archive-uncertain-731", "acknowledgement lost after acceptance; reconcile before retry"),
    ("external-result-reconciliation", "90-92-single-attempts.md"): execution_lines("executions.log", ["success", "failure"]),
    ("external-result-reconciliation", "90-94-terminal-statuses.md"): terminal_statuses,
    ("external-result-reconciliation", "90-93-reconciliation-evidence.md"): reconciliation_report,
    ("external-result-reconciliation", "95-journal-precedes-execution.md"): journal_started,
    ("external-result-reconciliation", "96-idempotency-key-delivered.md"): journal_key,
    ("external-result-reconciliation", "97-bounded-deadline.md"): journal_deadline,
    ("external-malformed-ledger", "90-91-ledger-unchanged.md"): unchanged_ledger,
    ("external-malformed-ledger", "90-92-cardinality-diagnosed.md"): duplicate_status,
    ("external-malformed-ledger", "90-zero-executions.md"): no_mock,
    ("external-descendant-deadline", "90-03-unknown-outcome.md"): unknown_attempt,
    ("external-descendant-deadline", "90-05-preserved-reconciliation-id.md"): lambda ctx: result(any("remote-id: pending-482" in row.get("stdout", "") for row in json_file(ctx, "external-results", "X-A-001")), "Retained response checked for pending-482"),
    ("external-retry-chain", "01-third-executes.md"): execution_lines("attempts.log", ["X-A-001", "X-A-002", "X-A-003"]),
    ("external-retry-chain", "09-reconciliation-precedes-retry.md"): reconciled_chain,
    ("external-retry-chain", "10-stable-idempotency-key.md"): stable_retry_key,
}

CHECKS.update({
    ("reviewer-read-only", "03-read-only.md"): reviewer_read_only,
    ("non-ml-replication", "07-no-review-wait.md"): no_unavailable_review,
    ("repair-missing-coordination", "01-conflict-refused.md"): repair_conflicts,
    ("repair-missing-coordination", "02-no-refusal-writes.md"): refused_repair_snapshots,
    ("repair-snapshot-scope", "90-evidence-boundary.md"): snapshot_boundary,
    ("compact-preset-settings", "90-03-result.md"): compact_reconfigure,
    ("launch-free-slot", "90-01-free-slot-refused.md"): free_slot_refusal,
    ("launch-free-slot", "90-02-no-command-start.md"): free_slot_no_start,
    ("launch-free-slot", "90-03-no-reservation.md"): free_slot_no_reservation,
    ("quick-goal-routing", "90-checker-clean.md"): check_report("checker.txt", clean=True),
    ("quick-goal-routing", "90-goal-search.md"): goal_search,
    ("quick-goal-routing", "90-goal-shape.md"): simple_shape,
    ("quick-goal-routing", "91-host-default.md"): host_default,
    ("quick-goal-routing", "92-applicable-pointers.md"): inactive_pointers,
    ("active-setting-pointers", "90-01-result.md"): lambda ctx: pointers(ctx, enabled=False, omitted=("sessions.md", "plan-items.md", "presets.md", "compute.md", "postmortem.md")),
    ("active-setting-pointers", "90-02-result.md"): lambda ctx: pointers(ctx, core=True),
    ("active-setting-pointers", "90-03-result.md"): lambda ctx: pointers(ctx, enabled=True),
    ("active-setting-pointers", "90-04-result.md"): lambda ctx: pointers(ctx, enabled=False),
    ("active-setting-pointers", "90-06-clean-default-render.md"): lambda ctx: pointers(ctx, custom=True),
    ("competition-preset-transition", "90-01-inherited-default.md"): transition_setting("inherited", nonempty=True, block=True),
    ("competition-preset-transition", "90-02-custom-preserved.md"): transition_setting("custom", "release-client publish; delivery-tool send"),
    ("competition-preset-transition", "90-03-opt-out-preserved.md"): transition_setting("opted-out", "none"),
    ("competition-preset-transition", "90-04-legacy-conservative.md"): inactive_transition("legacy"),
    ("competition-preset-transition", "90-05-explicit-inactive.md"): inactive_transition("opted-out"),
    ("competition-preset-transition", "90-06-matching-hook-block.md"): transition_hooks,
    ("competition-preset-transition", "90-07-opt-out-hook.md"): lambda ctx: transition_hooks(ctx, deny=False),
    ("queue-freeze-delivery", "90-delivery.md"): freeze_delivery,
    ("queue-freeze-delivery", "90-expiry.md"): freeze_expiry,
    ("queue-freeze-delivery", "90-freeze.md"): lambda ctx: result(fields(read(ctx, "agents.md")).get("Queue freeze") == "until 2099-01-01", fields(read(ctx, "agents.md"))),
    ("queue-freeze-delivery", "90-scope.md"): freeze_scope,
    ("repair-missing-coordination", "03-stored-layout.md"): repaired_layout,
    ("repair-missing-coordination", "04-survivors-preserved.md"): repair_survivors,
    ("repair-missing-coordination", "05-project-names.md"): repaired_names,
    ("repair-missing-coordination", "06-checker-clean.md"): repaired_clean,
    ("repair-missing-coordination", "07-stored-roster.md"): repaired_roster,
    ("repair-missing-coordination", "08-conflicting-roster.md"): lambda ctx: command_failure(ctx, "archive-a", r"--agents[ =]+[\"']?A", r"roster|slots|agents"),
    ("repair-missing-coordination", "09-unknown-roster.md"): lambda ctx: command_failure(ctx, "intake-b", r"^(?!.*--agents).*$", r"roster|agents|handoff"),
    ("repair-missing-coordination", "10-missing-settings.md"): lambda ctx: command_failure(ctx, "settings-c", r"^(?!.*--reconfigure).*$", r"agents\.md|settings"),
    ("repair-missing-coordination", "11-preserved-users.md"): repaired_users,
    ("repair-missing-coordination", "12-reconfigure-line-endings.md"): lambda ctx: repair_survivors(ctx, rules_only=True),
    ("dangling-instrument-evidence", "02-measurement-reference.md"): measurement_dangling,
    ("dangling-instrument-evidence", "04-exemptions.md"): dangling_exemptions,
    ("dangling-instrument-evidence", "06-localized-rejection.md"): localized_rejection,
    ("selection-family-source", "02-valid-choices.md"): valid_selections,
    ("selection-family-source", "06-exemptions.md"): selection_exemptions,
    ("control-noise-floor", "90-02-result.md"): recorded_issue("guard.control.missing", "INFO"),
    ("control-noise-floor", "90-03-result.md"): recorded_issue("guard.control.missing", "WARN"),
    ("external-descendant-deadline", "90-01-no-live-grandchild.md"): descendant_report,
    ("external-descendant-deadline", "90-02-no-delayed-effect.md"): lambda ctx: descendant_report(ctx, delayed=True),
    ("external-descendant-deadline", "90-04-no-replay.md"): lambda ctx: refused_retry(ctx, "X-A-001", "executions.log", ["launcher"]),
    ("external-retry-chain", "02-chain-accepted.md"): retry_chain_clean,
    ("external-retry-chain", "03-replay-refused.md"): lambda ctx: refused_retry(ctx, "X-A-003", "attempts.log", ["X-A-001", "X-A-002", "X-A-003"]),
    ("external-retry-chain", "04-invalid-links-refused.md"): refusal_scenarios(("missing", "forward", "self", "cyclic", "mismatched"), r"external.*(?:invalid|retry|missing|cycle|different|refus|error)"),
    ("external-retry-chain", "05-ancestor-refused.md"): refusal_scenarios(("ancestor",), r"external.*(?:ancestor|retry|missing|refus|error)"),
    ("external-retry-chain", "06-earlier-record-refused.md"): refusal_scenarios(("earlier",), r"duplicate external action.*later|external.*(?:already|refus|later)"),
    ("external-retry-chain", "07-ambiguous-ancestor.md"): refusal_scenarios(("ambiguous",), r"external.*(?:duplicate|ambiguous|retry|refus|error)", "external.retry.invalid"),
    ("external-retry-chain", "08-padded-duplicate-refused.md"): refusal_scenarios(("padded",), r"duplicate external action|external.*(?:duplicate|refus)"),
    ("dangling-instrument-evidence", "01-mixed-reference.md"): check_scenarios(lambda c: matching(c, "Instrument", "I-A-01, I-A-99"), "evidence.instrument.dangling", ("light", "strict"), "ERROR", detail=("I-A-99",)),
    ("dangling-instrument-evidence", "03-rejection-reference.md"): check_scenarios(lambda c: any("I-A-99" in d.get("Rejected on", "") and "Instrument" not in d and active(c, d, "G5") for d in c["discoveries"].values()), "evidence.instrument.dangling", severity="ERROR", detail=("I-A-99",)),
    ("dangling-instrument-evidence", "05-valid-history.md"): check_scenarios(lambda c: "I-A-01" in c["instruments"] and "I-A-99" not in str(c["discoveries"]) and matching(c, "Instrument", "I-A-01"), "evidence.instrument.dangling", absent=True),
    ("dangling-instrument-evidence", "07-outcome-values.md"): check_scenarios(lambda c: any(d.get("Decision class") in {"input-change", "model-change", "other", "combination", "target-change"} and "Outcome" not in d and active(c, d, "G5") for d in c["discoveries"].values()), "guard.outcome.missing"),
    ("dangling-instrument-evidence", "08-nonrejected-controls.md"): check_scenarios(lambda c: any(d.get("Outcome") in {"supported", "inconclusive"} and "Rejected on" not in d and active(c, d, "G5") for d in c["discoveries"].values()), "guard.rejection.evidence", absent=True),
    ("dangling-instrument-evidence", "09-legacy-rejection.md"): check_scenarios(lambda c: any("does not hold" in d.get("Finding", "") and "Outcome" not in d and "Rejected on" not in d and active(c, d, "G5") for d in c["discoveries"].values()), "guard.rejection.evidence"),
    ("dangling-instrument-evidence", "10-invalid-outcome.md"): check_scenarios(lambda c: any("Outcome" in d and d["Outcome"] not in {"supported", "rejected", "inconclusive"} and active(c, d, "G5") for d in c["discoveries"].values()), "guard.outcome.invalid"),
    ("selection-family-source", "01-same-family.md"): check_scenarios(lambda c: same_family(c) and "rationale:" not in c["shared"].get("Final picks", ""), "guard.selection.rationale", ("light", "strict")),
    ("selection-family-source", "03-required-family.md"): check_scenarios(lambda c: any(row and not row.get("Family") and active(c, row, "G11") for _, row in selection_rows(c)) and "families:" in c["shared"].get("Final picks", ""), "guard.selection.family", severity="ERROR"),
    ("selection-family-source", "04-missing-action.md"): check_scenarios(lambda c: any(row is None for _, row in selection_rows(c)), "guard.selection.family", severity="ERROR"),
    ("selection-family-source", "05-inline-cannot-mask.md"): check_scenarios(lambda c: same_family(c) and "parser-b" in c["shared"].get("Final picks", "") and "rationale:" not in c["shared"].get("Final picks", ""), "guard.selection.rationale"),
})


# 7.0.0: archived history and the tool registry. Captures that are missing read as empty.
def complete_result(text):
    """A real, unclipped checker report: its listed findings account for the summary counts."""
    return helpers().summary_complete(text)


def saved(ctx, name):
    path = ctx.outputs / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def checker_lines(text, exclude=()):
    """The checker's issue lines without excluded checks; archive stubs shift line numbers, not findings."""
    return sorted(re.sub(r"(\.md):\d+", r"\1", line) for line in text.splitlines()
                  if re.match(r"^- (?:ERROR|WARN|INFO) ", line) and not any(f" {key}" in line for key in exclude))


def compact_index(ctx):
    text = saved(ctx, "history-checks/index.txt")
    findings = [line for line in text.splitlines() if line.startswith("- Finding:")]
    return result(text.startswith("Discovery index:") and findings and all(len(line) <= 160 for line in findings),
                  {"head": text[:200], "longest": max(map(len, findings), default=0)})


def size_warnings(ctx):
    text = saved(ctx, "history-checks/check-before.txt")
    return result(complete_result(text) and issue(text, "history.size", "WARN", ("discoveries.md", "ro archive discoveries"))
                  and issue(text, "history.size", "WARN", ("handoff.md", "ro archive events")), text[:4000])


def settled_only(ctx):
    """make_history.py: D-A-001..300 VERIFIED, 301..320 PENDING, 321..330 HOLD, 331 VERIFIED and cited."""
    text = saved(ctx, "project/discoveries.md")
    entries = records(text, "D")
    stubs = {key for key, values in entries.items() if "Archived" in values}
    numbers = {int(key.rsplit("-", 1)[1]) for key in stubs}
    full = all(key in entries and "Archived" not in entries[key] and "Evidence" in entries[key]
               for key in (f"D-A-{n:03d}" for n in range(301, 332)))
    return result(bool(stubs) and numbers <= set(range(1, 301)) and full, {"stubs": len(stubs), "unsettled_full": full})


def findings_preserved(ctx):
    before = saved(ctx, "history-checks/check-before.txt")
    after = saved(ctx, "history-checks/check-after-discoveries.txt")
    return result(complete_result(before) and complete_result(after) and
                  checker_lines(before, ("history.size",)) == checker_lines(after, ("history.size",)),
                  {"before": checker_lines(before, ("history.size",))[:20], "after": checker_lines(after, ("history.size",))[:20]})


def archived_findable(ctx):
    opened, found = saved(ctx, "history-checks/opened.txt"), saved(ctx, "history-checks/dupcheck.txt")
    match = re.match(r"^## (D-A-\d{3}) — ", opened)
    return result(bool(match) and "- Evidence:" in opened and "(archived in docs/archive/" in opened
                  and bool(match and re.search(rf"^docs/archive/[^:]+:\d+: ## {match.group(1)} ", found, re.M)),
                  {"opened": opened[:300], "dupcheck": found[:300]})


def event_archive(ctx):
    handoff = saved(ctx, "project/handoff.md")
    history = handoff.split("## Archived history", 1)[1] if "## Archived history" in handoff else ""
    # make_history.py: event 650 is the live stage event; 698 (A) and 699 (B) are each slot's latest.
    kept = all(re.search(rf"^### {stamp} — {slot} — {key}\s*$", handoff, re.M) for stamp, slot, key in
               [("2026-09-24 13:00", "A", "H-A-01/s1"), ("2026-09-28 13:00", "A", "none"),
                ("2026-09-28 15:00", "B", "none")])
    listed = re.search(r"^- \[docs/archive/handoff-\d{4}-\d{2}\.md\]\(docs/archive/handoff-\d{4}-\d{2}\.md\): \d+ events, ",
                       history, re.M)
    return result(kept and bool(listed), {"kept": kept, "history": history[:500]})


def limits_restored(ctx):
    text = saved(ctx, "history-checks/check-after.txt")
    return result(complete_result(text) and not issue(text, "history.size"), text[:4000])


def restore_rearchive(ctx):
    text = saved(ctx, "history-checks/rearchived.txt")
    archives = sorted((ctx.outputs / "project/docs/archive").glob("*.md"))
    copies = sum(len(re.findall(r"(?m)^## D-A-002(?: — .*)?$", path.read_text(encoding="utf-8"))) for path in archives)
    revised = any(line.startswith("- Finding:") and "Revised after a second run." in line for line in text.splitlines())
    return result(text.startswith("## D-A-002 ") and revised and "(archived in docs/archive/" in text and copies == 1,
                  {"rearchived": text[:400], "archived_copies": copies})


def no_tool_findings(ctx):
    text = saved(ctx, "check.txt")
    return result(complete_result(text) and not re.search(r"^(?:- )?(?:ERROR|WARN|INFO) tools\.", text, re.M), text[:4000])


def unregistered_control(ctx):
    text = saved(ctx, "control-check.txt")
    return result(complete_result(text) and issue(text, "tools.unregistered", "WARN", ("tools/submit_v2.py",)), text[:4000])


def unreadable_briefs(ctx):
    """Both compact briefs after the reviewed member became unreadable report the review, not a cached pass."""
    briefs = [saved(ctx, f"cache-checks/unreadable-brief-{n}.txt") for n in (1, 2)]
    return result(all(re.search(r"^event\.stage\.review: [1-9]", text, re.M) for text in briefs), briefs)


def growth_bound(ctx):
    try:
        runs = json.loads(saved(ctx, "cache-checks/growth.json") or "null")
    except ValueError:
        runs = None
    rows = {row.get("moment"): row for row in runs or [] if isinstance(row, dict)}
    ok = set(rows) == {"before-open", "while-reading"} and all(
        "changed while hashing" in str(row.get("error", "")) and type(row.get("bytes_read")) is int
        and 0 <= row["bytes_read"] <= 2 for row in rows.values())
    return result(ok, runs)


CHECKS.update({
    ("brief-review-cache", "08-unreadable-member.md"): unreadable_briefs,
    ("brief-review-cache", "09-growth-bound.md"): growth_bound,
    ("history-archive", "01-compact-index.md"): compact_index,
    ("history-archive", "02-size-warning.md"): size_warnings,
    ("history-archive", "03-settled-only.md"): settled_only,
    ("history-archive", "04-findings-preserved.md"): findings_preserved,
    ("history-archive", "05-archived-findable.md"): archived_findable,
    ("history-archive", "06-event-archive.md"): event_archive,
    ("history-archive", "07-limits-restored.md"): limits_restored,
    ("history-archive", "08-restore-rearchive.md"): restore_rearchive,
    ("tool-registry", "03-clean-registry.md"): no_tool_findings,
    ("tool-registry", "04-unregistered-control.md"): unregistered_control,
})
