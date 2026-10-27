"""Saved artifact checks for optional research state and installation runtime selection."""
from __future__ import annotations

from collections import Counter
import json
import re

CHECKS = {}
SUMMARY_FIELDS = {"Current best", "Active compute", "Plan collection"}
SCORE_FIELDS = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"}
NEUTRAL_CLASSES = {"outcome-definition-change", "method-change", "data-change", "combined", "operational", "other"}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: saved artifact predicate {passed}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False, f"{case}/{name}: missing or malformed artifact"
    CHECKS[case, name + ".md"] = check


def fields(text):
    return dict(re.findall(r"^- ([\w ]+):[ \t]*([^\r\n]+)", text, re.M))


def unfenced(text):
    return re.sub(r"(?ms)^```[^\n]*\n.*?^```[^\n]*(?:\n|$)", "", text)


def section(text, heading):
    match = re.search(r"^## " + re.escape(heading) + r"[^\n]*\n(.*?)(?=^## |\Z)", unfenced(text), re.M | re.S)
    return match[1] if match else ""


def record(text, identifier):
    match = re.search(r"^#{2,3} " + re.escape(identifier) + r"\b[^\n]*\n(.*?)(?=^#{1,3} |\Z)",
                      unfenced(text), re.M | re.S)
    return match[1] if match else ""


def argument(arguments, flag, expected):
    return isinstance(arguments, list) and any(
        value == flag and index + 1 < len(arguments) and arguments[index + 1] == expected
        for index, value in enumerate(arguments))


def summary_issues(ctx, name, severity):
    issues = ctx.data(name + "-check.json")
    if not isinstance(issues, list):
        return False
    rows = [row for row in issues if row.get("check") == "handoff.shared.missing" and row.get("field") in SUMMARY_FIELDS]
    return len(rows) == 3 and {row["field"] for row in rows} == SUMMARY_FIELDS and all(
        row["severity"] == severity for row in rows)


def research_item(ctx):
    plan = unfenced(ctx.text("team/plan.md"))
    records = re.findall(r"^### H-[A-Z]+-\d+\b[^\n]*\n(.*?)(?=^#{1,3} |\Z)", plan, re.M | re.S)
    if len(records) != 1:
        raise ValueError("one active study item required")
    return fields(records[0])


def preserved_research_fields(ctx):
    supplied = json.loads((ctx.case_dir / "files/scenarios.json").read_text(encoding="utf-8"))["team_item"]
    saved = research_item(ctx)
    return all(saved.get(field) == supplied[key] for field, key in
               (("Hypothesis", "hypothesis"), ("Evidence", "evidence"), ("Next test", "next_test")))


case = "research-queue-optional-summaries"
register(case, "01-compact-research", lambda c: all(
    bool(section(c.text(name + "/handoff.md"), "Shared state")) and
    not SUMMARY_FIELDS & fields(section(c.text(name + "/handoff.md"), "Shared state")).keys()
    for name in ("solo", "team")))
register(case, "02-optional-severity", lambda c: all(
    fields(c.text(name + "/agents.md")).get("Plan collector") == "off" and summary_issues(c, name, "INFO")
    for name in ("solo", "team")))
register(case, "03-explicit-queue", lambda c:
         argument(c.data("setup-results.json")["team"], "--preset", "team-research") and
         argument(c.data("setup-results.json")["team"], "--ordering", "queue") and
         re.search(r"^Ordering: queue$", c.text("team/plan.md").split("\n## ", 1)[0], re.M))
register(case, "04-research-fields", preserved_research_fields)
register(case, "05-score-free", lambda c: not SCORE_FIELDS & research_item(c).keys())
register(case, "06-queue-valid", lambda c: isinstance(c.data("team-check.json"), list) and not any(
    row.get("severity") == "ERROR" and row.get("check", "").startswith("plan.") for row in c.data("team-check.json")))
register(case, "07-collector-control", lambda c:
         fields(c.text("collector/agents.md")).get("Plan collector") == "Shell/worker" and
         summary_issues(c, "collector", "ERROR"))
register(case, "08-reconfigured-summaries", lambda c:
         SUMMARY_FIELDS <= fields(section(c.text("collector-reconfigured-handoff.md"), "Shared state")).keys())
register(case, "09-reconfigured-checker", lambda c:
         isinstance(c.data("collector-reconfigured-check.json"), list) and
         not any(row.get("check") == "handoff.shared.missing" for row in c.data("collector-reconfigured-check.json")))


def example_inventory(ctx):
    examples = ctx.checker_skill.parent.parent / "examples"
    actual = Counter((path.relative_to(examples).as_posix(), value)
                     for path in examples.rglob("*.md")
                     for value in re.findall(r"^- Decision class:[ \t]*([^\r\n]+)", path.read_text(encoding="utf-8"), re.M))
    observed = Counter((row["file"].replace("\\", "/").removeprefix("examples/"), row["value"])
                       for row in ctx.data("example-classes.json"))
    return bool(actual) and observed == actual and all(value in NEUTRAL_CLASSES for _, value in observed)


case = "neutral-new-decision-records"
for name, document, identifier, expected in (
    ("01-research-method", "research", "D-A-001", "method-change"),
    ("02-research-data", "research", "D-A-002", "data-change"),
    ("03-competition-outcome", "competition", "D-A-001", "outcome-definition-change"),
    ("04-competition-combined", "competition", "D-A-002", "combined"),
):
    register(case, name, lambda c, doc=document, rid=identifier, value=expected:
             fields(record(c.text(doc + "-discoveries.md"), rid)).get("Decision class") == value)
register(case, "05-neutral-examples", example_inventory)
register(case, "06-preserve-legacy", lambda c: c.unchanged_bytes("legacy-v2.md"))


case = "minimal-quick-self-guidance"
register(case, "01-minimal-command", lambda c:
         argument(c.data("setup-results.json")["quick_arguments"], "--preset", "quick") and
         argument(c.data("setup-results.json")["quick_arguments"], "--user", "operator") and
         not any(value.split("=", 1)[0] in {"--platforms", "--language"}
                 for value in c.data("setup-results.json")["quick_arguments"]))
register(case, "02-detected-host", lambda c:
         fields(c.text("quick/agents.md")).get("Platforms", "").split(" — ")[-1] == "Claude Code")
register(case, "03-inferred-language", lambda c: fields(c.text("quick/agents.md")).get("Language") == "en")
register(case, "04-self-guidance", lambda c:
         fields(c.text("quick/agents.md")).get("Verification") == "self" and all(
             "references/verification.md" not in c.text("quick/" + name) for name in ("agents.md", "discoveries.md")))
register(case, "05-review-control", lambda c:
         fields(c.text("reviewed/agents.md")).get("Verification") == "independent-review" and all(
             "references/verification.md" in c.text("reviewed/" + name) for name in ("agents.md", "discoveries.md")))


def platforms(text):
    value = fields(text).get("Platforms", "")
    return value.removeprefix("single — ")


register("custom-work-defaults", "01-result", lambda c:
         fields(c.text("plain/agents.md")).get("Profile") == "work" and
         fields(c.text("plain/agents.md")).get("Verification") == "self")
register("custom-work-defaults", "02-result", lambda c:
         all(platforms(c.text(name + "/agents.md")) == "Claude Code" for name in ("plain", "custom")))
register("custom-work-defaults", "03-result", lambda c:
         all(f"- {key}:" in c.text("plain/plan.md") for key in ("Goal", "Evidence", "Next test")) and
         not any(f"- {key}:" in c.text("plain/plan.md") for key in ("Impact", "Information", "Confidence", "Cost", "Priority")))
register("custom-work-defaults", "04-result", lambda c:
         fields(c.text("custom/agents.md")).get("Verification") == "independent-review")
register("custom-work-defaults", "05-result", lambda c:
         all(fields(c.text(name + "/agents.md")).get("Enforcement") == "block" and
             {part.strip() for part in fields(c.text(name + "/agents.md")).get("Block", "").split(",")} ==
             {"shell.background", "shell.heredoc", "jobs.mutate-bound", "publish.scan"}
             for name in ("plain", "custom")))


def solo_items(ctx):
    return re.findall(r"^### H-[A-Z]+-\d+[^\n]*\n(.*?)(?=^#{2,3} |\Z)",
                      ctx.text("project/plan.md").split("## Queue", 1)[1], re.M | re.S)


register("solo-queue-exclusive-resource", "01-result", lambda c:
         re.findall(r"^Ordering: (\w+)$", c.text("project/plan.md").split("## Queue", 1)[0], re.M) == ["queue"])
register("solo-queue-exclusive-resource", "02-result", lambda c:
         bool(solo_items(c)) and any("database" in item.lower() and not any(
             key in fields(item) for key in ("Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"))
             for item in solo_items(c)))
register("solo-queue-exclusive-resource", "03-result", lambda c:
         any(fields(item).get("Parallel") == "NO" and "database" in fields(item).get("Other", "").lower()
             for item in solo_items(c)))
