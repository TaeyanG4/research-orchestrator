"""Objective artifact checks for startup, installer and hook shortcut cases."""
from __future__ import annotations

import re

CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: saved artifact check {passed}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False, f"{case}/{name}: incomplete saved artifact evidence"
    CHECKS[case, name + ".md"] = check


def inventory(value):
    return (isinstance(value, dict) and bool(value) and
            all(isinstance(path, str) and re.fullmatch(r"[a-f0-9]{64}", digest or "")
                for path, digest in value.items()))


register("uninstall-flag-conflict", "01-conflict-refused", lambda c:
         c.data("uninstall-results.json")["refusal"]["exit_code"] != 0 and
         "--uninstall" in c.data("uninstall-results.json")["refusal"]["arguments"] and
         "--no-hooks" in c.data("uninstall-results.json")["refusal"]["arguments"] and
         "reconciles owned hooks" in c.data("uninstall-results.json")["refusal"]["stderr"])
register("uninstall-flag-conflict", "02-unchanged-inventory", lambda c:
         inventory(c.data("uninstall-results.json")["before"]) and
         c.data("uninstall-results.json")["before"] == c.data("uninstall-results.json")["after"] and
         any(name.endswith("scripts/ro.py") for name in c.data("uninstall-results.json")["before"]) and
         any(name.endswith("settings.json") for name in c.data("uninstall-results.json")["before"]))
register("uninstall-flag-conflict", "03-foreign-preserved", lambda c:
         c.data("uninstall-results.json")["ordinary_uninstall"]["exit_code"] == 0 and
         "foreign-formatter" in str(c.data("uninstall-results.json")["settings_after_uninstall"]))


def shim(c, mode):
    return c.data("install-results.json")[mode]


register("default-cli-shim", "01-default-usable", lambda c:
         shim(c, "default")["exit_code"] == 0 and shim(c, "default")["shim_exists"] is True and
         "--shim" not in shim(c, "default")["arguments"] and
         "--no-shim" not in shim(c, "default")["arguments"] and
         shim(c, "default")["help_exit_code"] == 0 and
         "Research Orchestrator" in shim(c, "default")["help_stdout"])
register("default-cli-shim", "02-optout-absent", lambda c:
         shim(c, "optout")["exit_code"] == 0 and shim(c, "optout")["shim_exists"] is False and
         "--no-shim" in shim(c, "optout")["arguments"])
register("default-cli-shim", "03-explicit-compatible", lambda c:
         shim(c, "compatibility")["exit_code"] == 0 and
         shim(c, "compatibility")["shim_exists"] is True and "--shim" in shim(c, "compatibility")["arguments"])
register("default-cli-shim", "04-other-scope-preserved", lambda c:
         shim(c, "scope_control")["exit_code"] == 0 and
         re.fullmatch(r"[a-f0-9]{64}", shim(c, "scope_control")["before"]) and
         shim(c, "scope_control")["before"] == shim(c, "scope_control")["after"])


def startup(c, name):
    return c.data("startup-results.json")[name]


def registered(c, name):
    row = startup(c, name)
    return row["mapping"] == {"slot": "B"} and "Slot B:" in str(row["response"])


def unregistered(c, name, *, guide=True):
    row = startup(c, name)
    return row["mapping"] is None and (not guide or "Slot not selected" in str(row["response"]))


register("automatic-session-registration", "01-free-registered", lambda c:
         registered(c, "unique_free") and
         re.fullmatch(r"H-B-\d+", startup(c, "unique_free")["next_id"].strip()))
register("automatic-session-registration", "02-user-registered", lambda c:
         registered(c, "payload_user") and registered(c, "environment_user"))
register("automatic-session-registration", "03-ambiguous-unregistered", lambda c:
         unregistered(c, "ambiguous") and
         str(startup(c, "ambiguous")["response"]).count("?") == 1 and
         all(option in str(startup(c, "ambiguous")["response"]) for option in
             ("Continue slot ", "Start a new slot for parallel work", "Use slot <X>")))
register("automatic-session-registration", "04-other-unregistered", lambda c:
         unregistered(c, "other_users") and not re.search(r"Slot [A-Z]+:", str(startup(c, "other_users")["response"])))
register("automatic-session-registration", "05-unidentified-unregistered", lambda c:
         unregistered(c, "no_identity", guide=False))
register("automatic-session-registration", "06-handoff-preserved", lambda c:
         all(re.fullmatch(r"[a-f0-9]{64}", startup(c, name)["handoff_before"]) and
             startup(c, name)["handoff_before"] == startup(c, name)["handoff_after"]
             for name in ("unique_free", "payload_user", "environment_user", "ambiguous", "other_users", "no_identity")))


def quiet_rows(c, names, expected, event="PreToolUse"):
    rows = c.data("quiet-results.json")
    for tool in ("Edit", "Write"):
        for name in names:
            matching = [row for row in rows if (row.get("tool"), row.get("event"), row.get("registry")) ==
                        (tool, event, name)]
            if len(matching) != 1 or matching[0].get("quiet") is not expected:
                return False
    return True


register("hook-runtime-shortcuts", "01-quiet-safe", lambda c:
         quiet_rows(c, ("absent", "empty", "finished"), True))
register("hook-runtime-shortcuts", "02-active-checked", lambda c:
         quiet_rows(c, ("running", "attention", "unverified-tree"), False))
register("hook-runtime-shortcuts", "03-damaged-checked", lambda c:
         quiet_rows(c, ("malformed", "recovery"), False))
register("hook-runtime-shortcuts", "04-post-checked", lambda c:
         quiet_rows(c, ("empty",), False, "PostToolUse"))
register("hook-runtime-shortcuts", "05-deadline-retained", lambda c:
         all(re.search(pattern, c.text("runtime-report.md"), re.I) for pattern in
             (r"RO_HOOK_PYTHON", r"watchdog", r"(?:nine|9)[ -]second", r"(?:child|subprocess).*fallback")) and
         re.search(r"(?:no|not|without|unrun).{0,35}host.{0,10}probe|host.{0,10}probe.{0,30}(?:not|unrun)",
                   c.text("runtime-report.md"), re.I))
