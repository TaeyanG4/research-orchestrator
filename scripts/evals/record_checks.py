"""Active-record artifacts preserve history independently of live ownership."""

import re


CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: artifact predicate {passed}"
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return False, f"{case}/{name}: missing or malformed artifact"
    CHECKS[case, name + ".md"] = check


def archived(data):
    match = re.search(rb"(?m)^## Archived history\r?\n", data)
    if not match:
        raise ValueError("Archived section missing")
    following = re.search(rb"(?m)^#{1,2} ", data[match.end():])
    end = match.end() + following.start() if following else len(data)
    return data[match.start():end]


register("active-record-history", "03-live-brief", lambda c:
         "Slot A: taken; claims 1" in c.text("brief.txt") and
         re.findall(r"(?m)^Claim (H-[A-Z]+-\d+):", c.text("brief.txt")) == ["H-A-02"])
register("active-record-history", "04-close-live-only", lambda c:
         all(line in c.text("close.txt").splitlines() for line in
             ("Released claims: H-A-02", "Slot A: released", "Open claims: none")))
register("active-record-history", "05-history-byte-preservation", lambda c:
         all(archived((c.case_dir / "files" / name).read_bytes()) ==
             archived((c.outputs / "archive-project" / name).read_bytes())
             for name in ("plan.md", "handoff.md")))


def fields(text):
    return dict(re.findall(r"^- ([\w ]+):\s*([^\n]+)", text, re.M))


def block(text, identifier):
    match = re.search(r"^#{2,3} " + re.escape(identifier) + r"\b[^\n]*\n(.*?)(?=^#{2,3} |\Z)", text, re.M | re.S)
    return match[1] if match else ""


def original_reviews(ctx):
    return [line for line in (ctx.case_dir / "files/records.md").read_text(encoding="utf-8").splitlines()
            if re.match(r"\s+- .*: CLOSED", line)]


register("review-session-chronology", "01-older-session-accepted", lambda c:
         fields(block(c.text("project/discoveries.md"), "D-A-001")).get("Cross-check") == "VERIFIED" and
         original_reviews(c)[0] in block(c.text("project/discoveries.md"), "D-A-001"))
for number, identifier, check in ((2, "D-A-002", "identity"), (3, "D-A-003", "time")):
    name = "02-future-identity-rejected" if number == 2 else "03-future-review-rejected"
    register("review-session-chronology", name, lambda c, identifier=identifier, check=check:
             any("discovery.review." + check in line and identifier in line for line in c.text("before.txt").splitlines()) and
             fields(block(c.text("project/discoveries.md"), identifier)).get("Cross-check") == "PENDING")
register("review-session-chronology", "04-history-preserved", lambda c:
         len(original_reviews(c)) == 3 and all(line in c.text("project/discoveries.md") for line in original_reviews(c)))
register("review-session-chronology", "06-offset-instants", lambda c:
         c.data("offsets.json") == [True, False] and all(type(value) is bool for value in c.data("offsets.json")))


