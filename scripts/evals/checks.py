"""Objective acceptance checks, keyed by the unmodified skill-creator grader filenames."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

if __package__:
    from .command_trace import ro_commands
    from .content import normalize_text
    from .evidence import HELPERS
    from .proc import no_window_flags
    from .replication_check import expected_replication, matches_replication, rerun_analysis
    from .work_checks import WORK_CHECKS
else:
    from command_trace import ro_commands
    from content import normalize_text
    from evidence import HELPERS
    from proc import no_window_flags
    from replication_check import expected_replication, matches_replication, rerun_analysis
    from work_checks import WORK_CHECKS


def digest(data: bytes) -> str:
    return hashlib.sha256(normalize_text(data)).hexdigest()


def matches_digest(data: bytes, expected: str) -> bool:
    # Historical receipts used checkout bytes; new receipts use canonical text.
    canonical = normalize_text(data)
    digests = {digest(canonical), hashlib.sha256(data).hexdigest()}
    legacy = canonical.replace(b"\n", b"\r\n")
    if normalize_text(legacy) == canonical:
        digests.add(hashlib.sha256(legacy).hexdigest())
    return expected in digests


@dataclass
class CheckContext:
    case_dir: Path
    run_dir: Path
    checker_skill: Path
    python: str

    @property
    def outputs(self) -> Path:
        return self.run_dir / "outputs"

    def text(self, name: str) -> str:
        return (self.outputs / name).read_text(encoding="utf-8")

    def data(self, name: str):
        return json.loads(self.text(name))

    def unchanged(self, name: str) -> bool:
        return normalize_text((self.case_dir / "files" / name).read_bytes()) == normalize_text(
            (self.outputs / name).read_bytes())

    def unchanged_bytes(self, name: str) -> bool:
        """Preservation promises include the source file's original line endings."""
        return (self.case_dir / "files" / name).read_bytes() == (self.outputs / name).read_bytes()

    def execution(self, helper: str) -> tuple[bool, str]:
        """Only the harness can append this log or populate its capture tree."""
        try:
            records = [json.loads(line) for line in (self.run_dir / "evidence.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]
            if len(records) != 1:
                return False, f"Expected one trusted helper execution, found {len(records)}"
            record = records[0]
            request = record.get("request", "")
            invocations = [json.loads(line) for line in (self.run_dir / "helper-executions.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]
            if len(invocations) != 1:
                return False, f"Expected one helper invocation including denied attempts, found {len(invocations)}"
            invocation = invocations[0]
            if (invocation.get("sequence") != 1 or invocation.get("request") != request
                    or invocation.get("helper") != helper or invocation.get("mode") != "request"):
                return False, "Helper invocation authorization or ordering is invalid"
            if (record.get("helper") != helper or not re.fullmatch(r"[0-9a-f]{32}", request)
                    or record.get("returncode") != 0 or record.get("error") is not None
                    or not matches_digest((self.case_dir / "files" / helper).read_bytes(),
                                          record.get("helper_sha256"))):
                return False, "Trusted helper identity or successful completion is missing"
            registered = HELPERS.get(self.case_dir.name)
            if not registered or registered[0] != helper:
                return False, "Helper is not registered for this case"
            if helper == "measure_posttool.py":
                # Acceptance uses the current checker for both configurations;
                # execution must still belong to that run's selected runtime.
                run = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
                runtime = run.get("evidence", {}).get("runtime_sha256", "")
                if not re.fullmatch(r"[0-9a-f]{64}", runtime) or record.get("runtime_sha256") != runtime:
                    return False, "Measurement runtime differs from the evaluated runtime"
                collector = Path(__file__).with_name("posttool_capture.py").read_bytes()
                if not matches_digest(collector, record.get("collector_sha256")):
                    return False, "Measurement collector identity is missing or differs"
            artifacts = record.get("artifacts", {})
            if set(artifacts) != set(registered[2]):
                return False, "Trusted helper receipt is incomplete"
            capture = self.run_dir / "evidence" / request
            for name, expected_digest in artifacts.items():
                original = (capture / name).read_bytes()
                if (not matches_digest(original, expected_digest)
                        or normalize_text((self.outputs / name).read_bytes()) != normalize_text(original)):
                    return False, f"Captured artifact was altered after execution: {name}"
            return True, f"One successful canonical {helper} execution; all captured artifacts match"
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            return False, f"Trusted execution evidence unavailable: {exc}"

    @cached_property
    def transcript(self) -> str:
        return (self.run_dir / "transcript.md").read_text(encoding="utf-8")

    @cached_property
    def completed_commands(self) -> list[dict]:
        executions = []
        for line in (self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            item = event.get("item", {})
            if (event.get("type") == "item.completed" and isinstance(item, dict)
                    and item.get("type") == "command_execution"):
                executions.append(item)
        return executions

    @cached_property
    def executions(self) -> list[dict]:
        """Successful commands, for assertions that require work to have completed."""
        return [item for item in self.completed_commands if item.get("exit_code") == 0]

    @cached_property
    def ro_commands(self):
        return ro_commands(self.executions)


def unfenced(text: str) -> str:
    """Mask fenced examples while retaining offsets for raw history comparisons."""
    lines, fence, width = [], None, 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence is None and marker:
            fence, width = marker[1][0], len(marker[1])
        elif (fence is not None and marker and marker[1][0] == fence
              and len(marker[1]) >= width and not marker[2].strip()):
            fence = None
        elif fence is None:
            lines.append(line)
            continue
        lines.append(re.sub(r"[^\r\n]", " ", line))
    return "".join(lines)


def fields(text: str) -> dict[str, str]:
    return dict(re.findall(r"^- ([^:\n]+):[ \t]*([^\n]*)", unfenced(text), re.M))


def blocks(text: str, prefix: str) -> dict[str, str]:
    pattern = rf"^#{{2,3}} ({prefix}-[A-Z]+-\d+)\b[^\n]*\n(?:(?!^#{{1,3}} ).*(?:\n|$))*"
    return {match.group(1): text[match.start():match.end()]
            for match in re.finditer(pattern, unfenced(text), re.M)}


def slot(text: str) -> dict[str, str]:
    match = re.search(r"^### Agent: A\s*\n(.*?)(?=^#{1,3} |\Z)", unfenced(text), re.M | re.S)
    return fields(match.group(1)) if match else {}


def events(text: str, item: str | None = None) -> list[str]:
    pattern = r"^### \d{4}-\d{2}-\d{2} [^\n]*\n.*?(?=^#{1,3} |\Z)"
    records = [text[match.start():match.end()] for match in re.finditer(pattern, unfenced(text), re.M | re.S)]
    return [record for record in records if item is None or re.search(rf"\b{re.escape(item)}\s*$", record.splitlines()[0])]


def checker_clean(ctx: CheckContext) -> tuple[bool, str]:
    result = subprocess.run(
        [ctx.python, str(ctx.checker_skill / "scripts" / "check_project.py"), str(ctx.outputs)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=no_window_flags())
    evidence = (result.stdout + result.stderr).strip()
    (ctx.run_dir / "checker.txt").write_text(evidence + "\n", encoding="utf-8")
    return result.returncode == 0 and "CONSISTENCY:" in result.stdout, f"Checker exit {result.returncode}: {evidence[:6000]}"


def work_preset(ctx: CheckContext) -> tuple[bool, str]:
    settings = fields(ctx.text("agents.md"))
    expected = {"Preset": "work-project", "Profile": "work", "Workflow": "unified", "Item size": "staged"}
    actual = {key: settings.get(key) for key in expected}
    return actual == expected, f"agents.md settings: {actual}"


def staged_queue(ctx: CheckContext) -> tuple[bool, str]:
    items = {key: fields(value) for key, value in blocks(ctx.text("plan.md"), "H").items()}
    valid = len(items) >= 2 and all(
        item.get("Claimed") == "none" and len(set(re.findall(r"\bs\d+\b", item.get("Stages", "")))) >= 2
        and (item.get("Next test") or item.get("Next step"))
        and (item.get("Hypothesis") or item.get("Goal"))
        and item.get("Evidence") for item in items.values())
    return bool(valid), f"plan.md has {len(items)} items; Claimed/Stages/context: {items}"


def brief_preserved(ctx: CheckContext) -> tuple[bool, str]:
    same = ctx.unchanged_bytes("brief.md")
    return same, f"brief.md byte-for-byte unchanged, including line endings: {same}"


def claim_recorded(ctx: CheckContext) -> tuple[bool, str]:
    executed, evidence = ctx.execution("analyze.py")
    if not executed:
        return False, evidence
    snapshot = ctx.outputs / "results" / "claim-before.md"
    if snapshot.exists():
        item = blocks(snapshot.read_text(encoding="utf-8"), "H").get("H-A-01", "")
        claimed = fields(item).get("Claimed", "")
        return (bool(re.match(r"A\b", claimed)) and ctx.unchanged("analyze.py")
                and ctx.unchanged("observations.csv")), f"Claim at analysis start: {claimed}; {evidence}"
    return False, "Missing results/claim-before.md snapshot from the supplied analysis script"


def discovery_followups(ctx: CheckContext) -> tuple[bool, str]:
    discoveries = blocks(ctx.text("discoveries.md"), "D")
    items = blocks(ctx.text("plan.md"), "H")
    summary = ctx.data("results/summary.json")
    measured = (summary.get("n") == 6 and summary.get("overall_mean") == 6
                and summary.get("source_means") == {"alpha": 3, "beta": 9})
    followup = fields(items.get("H-A-02", ""))
    cited = {key: record for key, record in discoveries.items()
             if "results/summary.json" in fields(record).get("Evidence", "")
             and key in followup.get("Sources", "")}
    findings = {}
    for key, record in cited.items():
        try:
            findings[key] = json.loads(fields(record).get("Finding", ""))
        except ValueError:
            findings[key] = None
    valid = measured and bool(cited) and all(finding == summary for finding in findings.values()) and all(
        followup.get(field, "").lower() not in {"", "none", "tbd", "n/a"} for field in ("Evidence", "Improvement"))
    return valid, f"Summary: {summary}; structured findings: {findings}; H-A-02: {followup}"


def closed_consistently(ctx: CheckContext) -> tuple[bool, str]:
    active = slot(ctx.text("handoff.md"))
    claims = {key: fields(value).get("Claimed") for key, value in blocks(ctx.text("plan.md"), "H").items()}
    valid = active.get("Current host") == "released" and active.get("Current user") == "none" and all(
        value == "none" for value in claims.values())
    return valid, f"Slot A: {active}; queue claims: {claims}"


def resume_closed(ctx: CheckContext) -> tuple[bool, str]:
    closed, details = closed_consistently(ctx)
    items = blocks(ctx.text("plan.md"), "H")
    sources = fields(items.get("H-A-02", "")).get("Sources", "")
    completion = [fields(event) for event in events(ctx.text("handoff.md"), "H-A-01")]
    linked = any("H-A-02" in event.get("New plan items", "") and any(
        disc in sources for disc in re.findall(r"D-[A-Z]+-\d+", event.get("Discovery updates", ""))) for event in completion)
    valid = closed and "H-A-01" not in items and "H-A-02" in items and linked
    return valid, f"{details}; H-A-01 removed: {'H-A-01' not in items}; completion events: {completion}"


def rules_region(data: bytes) -> bytes:
    data = normalize_text(data)
    match = re.search(rb"(?m)^## Project rules\r?$", data)
    if not match:
        raise ValueError("## Project rules region is absent")
    following = re.search(rb"(?m)^## (?!#)", data[match.end():])
    end = match.end() + following.start() if following else len(data)
    return data[match.start():end]


def rules_preserved(ctx: CheckContext) -> tuple[bool, str]:
    before = rules_region((ctx.case_dir / "files" / "agents.md").read_bytes())
    after = rules_region((ctx.outputs / "agents.md").read_bytes())
    return before == after, f"Project rules bytes before/after: {len(before)}/{len(after)}; SHA256 {hashlib.sha256(before).hexdigest()}/{hashlib.sha256(after).hexdigest()}"


def upgraded_queue(ctx: CheckContext) -> tuple[bool, str]:
    agents = ctx.text("agents.md")
    settings = fields(agents)
    item = fields(blocks(ctx.text("plan.md"), "H").get("H-A-01", ""))
    valid = ("ro-template: v3." in agents and settings.get("Profile") == "research"
             and settings.get("Workflow") == "unified" and item.get("Claimed") == "none")
    return valid, f"Template v3: {'ro-template: v3.' in agents}; Workflow {settings.get('Workflow')}; H-A-01: {item}"


def history_preserved(ctx: CheckContext) -> tuple[bool, str]:
    original_discoveries = (ctx.case_dir / "files" / "discoveries.md").read_text(encoding="utf-8")
    before = blocks(original_discoveries, "D").get("D-A-001", "").strip()
    after = blocks(ctx.text("discoveries.md"), "D").get("D-A-001", "").strip()
    source_handoff = (ctx.case_dir / "files" / "handoff.md").read_text(encoding="utf-8")
    events = re.findall(r"^### \d{4}-\d{2}-\d{2} .*?\n.*?(?=^#{1,3} |\Z)", source_handoff, re.M | re.S)
    retained = bool(events) and all(event.strip() in ctx.text("handoff.md") for event in events)
    return bool(before) and before == after and retained, f"D-A-001 unchanged: {bool(before) and before == after}; {len(events)} original events retained: {retained}"


def preaction_ledger(ctx: CheckContext) -> tuple[bool, str]:
    executed, evidence = ctx.execution("simulate_external.py")
    if not executed:
        return False, evidence
    action = fields(blocks(ctx.text("action-before.md"), "X").get("X-A-001", ""))
    expected = action.get("Expected", "")
    valid = bool(expected) and expected.lower() not in {"pending", "none"} and action.get("Result") == "pending" and action.get("Status") == "prepared"
    # The protected receipt proves this snapshot came from the canonical helper.
    result = ctx.data("action-result.json")
    valid &= ctx.unchanged("simulate_external.py") and matches_digest(
        (ctx.outputs / "action-before.md").read_bytes(), result.get("before_sha256"))
    return valid, f"Snapshot X-A-001 fields: {action}; {evidence}"


def action_integrity(ctx: CheckContext) -> tuple[bool, str]:
    executed, evidence = ctx.execution("simulate_external.py")
    if not executed:
        return False, evidence
    result = ctx.data("action-result.json")
    candidate = (ctx.outputs / "release-note.txt").read_bytes()
    snapshot = (ctx.outputs / "action-before.md").read_bytes()
    valid = (ctx.unchanged("simulate_external.py") and ctx.unchanged("release-note.txt")
             and matches_digest(snapshot, result.get("before_sha256"))
             and matches_digest(candidate, result.get("candidate_sha256"))
             and result.get("executions") == 1 and result.get("status") == "accepted")
    return valid, f"action-result.json: {result}; {evidence}; candidate={digest(candidate)}, snapshot={digest(snapshot)}"


def action_result(ctx: CheckContext) -> tuple[bool, str]:
    executed, evidence = ctx.execution("simulate_external.py")
    if not executed:
        return False, evidence
    before = fields(blocks(ctx.text("action-before.md"), "X").get("X-A-001", ""))
    after = fields(blocks(ctx.text("handoff.md"), "X").get("X-A-001", ""))
    candidate = (ctx.outputs / "release-note.txt").read_bytes()
    candidates = re.findall(r"\b[0-9a-f]{64}\b", after.get("Candidate", ""), re.I)
    valid = (any(matches_digest(candidate, value.lower()) for value in candidates)
             and before.get("Candidate") == after.get("Candidate")
             and before.get("Destination") == after.get("Destination") == "mock://archive/release-note"
             and "accepted" in after.get("Result", "").lower() and after.get("Status") in {"done", "complete"})
    return valid, f"Final X-A-001: {after}; preserved candidate/destination: {valid}"


def owned_job(ctx: CheckContext) -> tuple[bool, str]:
    jobs = ctx.data(".ro/jobs.json")
    entries = [job for job in jobs if job.get("item") == "H-A-01" and job.get("slot") == "A"]
    result = ctx.data("runs/owned/job-result.json")
    valid = ctx.unchanged("simulate_job.py") and result.get("status") == "completed" and any(
        job.get("confirmed") is True and job.get("pid") and job.get("start") and job.get("status") == "finished"
        and job.get("exit_code") == 0 and any(command.subcommand == "launch" and command.job == job.get("id")
                                             for command in ctx.ro_commands) for job in entries)
    return bool(valid), f"Owned H-A-01 job records: {entries}"


def monitored_job(ctx: CheckContext) -> tuple[bool, str]:
    entries = [job for job in ctx.data(".ro/jobs.json") if job.get("item") == "H-A-01" and job.get("slot") == "A"]
    valid = any(job.get("status") == "finished" and (job.get("monitor") or {}).get("reason")
                and any(command.subcommand == "monitor" and command.job == job.get("id")
                        for command in ctx.ro_commands) for job in entries)
    return valid, f"Job monitor records: {[job.get('monitor') for job in entries]}; resolved commands: {ctx.ro_commands}"


def closed_after_completion(ctx: CheckContext) -> tuple[bool, str]:
    closed, details = closed_consistently(ctx)
    owned = {job.get("id") for job in ctx.data(".ro/jobs.json")
             if job.get("item") == "H-A-01" and job.get("slot") == "A"
             and job.get("status") == "finished" and (job.get("monitor") or {}).get("reason")}
    observe = [command.position for command in ctx.ro_commands if command.subcommand == "monitor" and command.job in owned]
    close = [command.position for command in ctx.ro_commands if command.subcommand == "close"]
    rows = ctx.data("runs/owned/ownership-samples.json")
    result = ctx.data("runs/owned/job-result.json")
    start, end = datetime.fromisoformat(result["started_at"]), datetime.fromisoformat(result["completed_at"])
    samples_valid = (len(rows) >= 3 and result.get("sample_count") == len(rows) and (end - start).total_seconds() >= 6
                     and all(row.get("current_host") not in {None, "", "released", "unassigned"}
                             and row.get("current_user") not in {None, "", "none"}
                             and re.match(r"A\b", row.get("claim") or "")
                             and start <= datetime.fromisoformat(row["sampled_at"]) <= end for row in rows))
    ordered = bool(observe and close) and min(close) > min(observe)
    valid = closed and ordered and samples_valid and ctx.unchanged("simulate_job.py") and result.get("status") == "completed"
    return bool(valid), f"Monitor indices {observe}; close indices {close}; {len(rows)} ownership samples valid: {bool(samples_valid)}; result: {result}; {details}"


def direction_records(ctx: CheckContext) -> dict[str, dict]:
    return {key: fields(value) for key, value in blocks(ctx.text("discoveries.md"), "D").items()
            if fields(value).get("Kind") == "direction-review"}


def direction_review(ctx: CheckContext) -> tuple[bool, str]:
    reviews = direction_records(ctx)
    required = ("Gap", "Decomposition", "Core families", "Intake", "Rejected consistent gains", "Decisions", "Data audit")
    pointer = fields(ctx.text("handoff.md")).get("Last direction review", "")
    valid = any(key in pointer and all(review.get(field) for field in required) for key, review in reviews.items())
    return valid, f"Last direction review: {pointer}; reviews: {reviews}"


def saturation_addressed(ctx: CheckContext) -> tuple[bool, str]:
    items = {key: fields(value) for key, value in blocks(ctx.text("plan.md"), "H").items()}
    reviews = direction_records(ctx)
    instruments = blocks(ctx.text("handoff.md"), "I")
    saturated = {key: value for key, value in items.items() if value.get("Family") == "threshold-tuning"}
    def valid_exit(item):
        reason = item.get("Saturation exit", "")
        instrument = re.fullmatch(r"instrument (I-[A-Z]+-\d+)", reason)
        structural = re.fullmatch(r"structural: .+\(review (D-[A-Z]+-\d+)\)", reason)
        return bool((instrument and instrument[1] != "I-A-01" and instrument[1] in instruments)
                    or (structural and structural[1] in reviews))
    alternative = any(item.get("Family") not in {None, "", "threshold-tuning"} for item in items.values())
    structural = any(item.get("Saturation exit", "").startswith("structural:") and valid_exit(item) for item in saturated.values())
    return all(valid_exit(item) for item in saturated.values()) and (alternative or structural), f"Remaining threshold-tuning items: {saturated}; alternative: {alternative}; reviews: {list(reviews)}"


def decision_followup(ctx: CheckContext) -> tuple[bool, str]:
    reviews = direction_records(ctx)
    logged = [fields(event) for event in events(ctx.text("handoff.md"))]
    linked = [event for event in logged if any(review in event.get("Discovery updates", "") for review in reviews)
              and (re.search(r"H-[A-Z]+-\d+", event.get("New plan items", ""))
                   or re.search(r"removed H-[A-Z]+-\d+", event.get("Action", ""), re.I))]
    before = blocks((ctx.case_dir / "files" / "discoveries.md").read_text(encoding="utf-8"), "D")
    after = blocks(ctx.text("discoveries.md"), "D")
    retained = len(before) == 5 and all(after.get(key, "").strip() == value.strip() for key, value in before.items())
    return bool(linked) and retained, f"Decision events: {linked}; original five discoveries unchanged: {retained}"


def numeric_replication(ctx: CheckContext) -> tuple[bool, str]:
    result = ctx.data("replication.json")
    expected = expected_replication(ctx.case_dir / "files")
    return matches_replication(result, expected), f"replication.json: {result}; independently calculated: {expected}"


def evidence_followups(ctx: CheckContext) -> tuple[bool, str]:
    discoveries = blocks(ctx.text("discoveries.md"), "D")
    findings = {key: fields(value) for key, value in discoveries.items()
                if "replication.json" in fields(value).get("Evidence", "")}
    completion = [fields(event) for event in events(ctx.text("handoff.md"), "H-A-01")]
    explicit = any(any(key in event.get("Discovery updates", "") for key in findings)
                   and (re.search(r"\bH-[A-Z]+-\d+\b", event.get("New plan items", ""))
                        or re.match(r"none\s+[—–-]\s+\S", event.get("New plan items", ""))) for event in completion)
    code = [name for finding in findings.values() for name in re.findall(r"[\w./-]+\.py\b", finding.get("Evidence", ""))
            if not Path(name).is_absolute() and ".." not in Path(name).parts
            and (ctx.outputs / name).is_file() and normalize_text((ctx.outputs / name).read_bytes())]
    reruns = {name: rerun_analysis(ctx, name) for name in dict.fromkeys(code)} if findings and explicit else {}
    return bool(findings and explicit and any(result[0] for result in reruns.values())), (
        f"Evidence-linked findings: {findings}; reruns: {reruns}; completion: {completion}")


def neutral_workflow(ctx: CheckContext) -> tuple[bool, str]:
    profile = fields(ctx.text("agents.md")).get("Profile")
    # Instrument exclusions describe forbidden uses, not experiments performed.
    text = "\n".join(unfenced(ctx.text(name)) for name in ("plan.md", "discoveries.md", "handoff.md"))
    text = re.sub(r"^- Not for:[^\n]*", "", text, flags=re.M)
    jargon = re.findall(r"\b(?:predictive-model|model-change)\b", text, re.I)
    same = ctx.unchanged("measurements.csv") and ctx.unchanged("paper-excerpt.md")
    competition = fields(ctx.text("agents.md")).get("Competition")
    actions = blocks(ctx.text("handoff.md"), "X")
    return profile == "research" and competition == "off" and not jargon and same and not actions, f"Profile: {profile}; Competition: {competition}; jargon: {jargon}; inputs unchanged: {same}; external actions: {list(actions)}"


def review_pending(ctx: CheckContext) -> tuple[bool, str]:
    findings = {key: value for key, value in blocks(ctx.text("discoveries.md"), "D").items()
                if "replication.json" in fields(value).get("Evidence", "")}
    policy = fields(ctx.text("agents.md")).get("Verification")
    pending = bool(findings) and all(fields(value).get("Cross-check") == "PENDING"
                                   and not re.search(r"^\s+- .+\([A-Z]+\):", value, re.M)
                                   for value in findings.values())
    return pending and policy == "independent-review", f"Verification: {policy}; replication findings: {findings}"


def job_handoff(ctx: CheckContext) -> tuple[bool, str]:
    jobs = [job for job in ctx.data(".ro/jobs.json") if job.get("item") == "H-A-01" and job.get("slot") == "A"]
    lines = re.findall(r"^- Job: (J-[A-Z]+-\d+); item ([^;]+); outcome: (.+)$", ctx.text("handoff.md"), re.M)
    matched = [(job.get("id"), job.get("item"), (job.get("monitor") or {}).get("reason")) for job in jobs]
    return any(line in matched for line in lines), f"Handoff Job lines: {lines}; registry outcomes: {matched}"


def project_language(ctx: CheckContext) -> tuple[bool, str]:
    language = fields(ctx.text("agents.md")).get("Language")
    return language == "ko", f"Language: {language}"


def timing_comparison(ctx: CheckContext) -> tuple[bool, str]:
    with (ctx.case_dir / "files" / "timings.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    current = sum(float(row["current_seconds"]) for row in rows) / len(rows)
    candidate = sum(float(row["candidate_seconds"]) for row in rows) / len(rows)
    expected = {"count": len(rows), "mean_current_seconds": current,
                "mean_candidate_seconds": candidate, "saved_seconds": current - candidate}
    result = ctx.data("comparison.json")
    valid = ctx.unchanged("timings.csv") and all(
        type(result.get(key)) in {int, float} and math.isclose(result[key], value, rel_tol=0, abs_tol=1e-9)
        for key, value in expected.items())
    return valid, f"comparison.json: {result}; computed from original observations: {expected}"


_CASE_CHECKS = {
    "project-language": {"02-language-preserved": project_language, "06-comparison": timing_comparison},
    "work-project-start": {"02-work-preset": work_preset, "03-staged-queue": staged_queue, "04-brief-preserved": brief_preserved},
    "unified-research-resume": {"02-claim-recorded": claim_recorded, "03-discovery-follow-up": discovery_followups, "04-closed-session": resume_closed},
    "v2-rules-upgrade": {"02-rules-preserved": rules_preserved, "03-unified-upgrade": upgraded_queue, "04-records-preserved": history_preserved},
    "external-action-order": {"02-expectation-before-action": preaction_ledger, "03-ledger-reconciled": action_result, "04-single-execution": action_integrity},
    "owned-job-monitor": {"02-owned-job": owned_job, "03-monitored-job": monitored_job, "04-close-after-completion": closed_after_completion, "05-job-handoff": job_handoff},
    "competition-direction-review": {"02-direction-review": direction_review, "03-saturation-response": saturation_addressed, "04-decision-follow-up": decision_followup},
    "non-ml-replication": {"02-replication-math": numeric_replication, "03-replication-recorded": evidence_followups, "04-domain-appropriate": neutral_workflow, "05-review-pending": review_pending},
}
SCRIPTED_CHECKS = {(case, filename + ".md"): check for case, checks in _CASE_CHECKS.items()
                   for filename, check in {"01-checker-clean": checker_clean, **checks}.items()}
SCRIPTED_CHECKS.update({(case, filename + ".md"): check for case, checks in WORK_CHECKS.items()
                        for filename, check in checks.items()})
if __package__:
    from .deterministic_artifacts import CHECKS as ARTIFACT_CHECKS
    from .deterministic_checker_cases import CHECKS as CHECKER_CASE_CHECKS
else:
    from deterministic_artifacts import CHECKS as ARTIFACT_CHECKS
    from deterministic_checker_cases import CHECKS as CHECKER_CASE_CHECKS
SCRIPTED_CHECKS.update(ARTIFACT_CHECKS)
if __package__:
    from .host_artifacts import CHECKS as HOST_ARTIFACT_CHECKS
else:
    from host_artifacts import CHECKS as HOST_ARTIFACT_CHECKS
SCRIPTED_CHECKS.update(HOST_ARTIFACT_CHECKS)
SCRIPTED_CHECKS.update(CHECKER_CASE_CHECKS)
if __package__:
    from .audit_artifacts import CHECKS as AUDIT_ARTIFACT_CHECKS
else:
    from audit_artifacts import CHECKS as AUDIT_ARTIFACT_CHECKS
SCRIPTED_CHECKS.update(AUDIT_ARTIFACT_CHECKS)
if __package__:
    from .startup_artifacts import CHECKS as STARTUP_ARTIFACT_CHECKS
else:
    from startup_artifacts import CHECKS as STARTUP_ARTIFACT_CHECKS
SCRIPTED_CHECKS.update(STARTUP_ARTIFACT_CHECKS)
if __package__:
    from .runtime_boundary_artifacts import CHECKS as RUNTIME_BOUNDARY_CHECKS
else:
    from runtime_boundary_artifacts import CHECKS as RUNTIME_BOUNDARY_CHECKS
SCRIPTED_CHECKS.update(RUNTIME_BOUNDARY_CHECKS)
if __package__:
    from .stage_checks import CHECKS as STAGE_BOUNDARY_CHECKS
else:
    from stage_checks import CHECKS as STAGE_BOUNDARY_CHECKS
SCRIPTED_CHECKS.update(STAGE_BOUNDARY_CHECKS)

if __package__:
    from .document_checks import CHECKS as DOCUMENT_CHECKS
else:
    from document_checks import CHECKS as DOCUMENT_CHECKS
SCRIPTED_CHECKS.update(DOCUMENT_CHECKS)

if __package__:
    from .runtime_checks import CHECKS as RUNTIME_CHECKS
else:
    from runtime_checks import CHECKS as RUNTIME_CHECKS
SCRIPTED_CHECKS.update(RUNTIME_CHECKS)

if __package__:
    from .record_checks import CHECKS as RECORD_CHECKS
else:
    from record_checks import CHECKS as RECORD_CHECKS
SCRIPTED_CHECKS.update(RECORD_CHECKS)

if __package__:
    from .profile_checks import CHECKS as PROFILE_CHECKS
else:
    from profile_checks import CHECKS as PROFILE_CHECKS
SCRIPTED_CHECKS.update(PROFILE_CHECKS)
