"""Saved installation and hook artifacts; these checks never execute commands."""
from __future__ import annotations

import ast
import json
import re

if __package__:
    from .command_trace import _source, _statements
else:
    from command_trace import _source, _statements

CHECKS = {}

# Artifact predicates are necessary but cannot establish that an arbitrary
# harness actually called the requested runtime. These trace assertions are
# case-wide prerequisites in grade_evals, including for otherwise valid JSON.
EXECUTION_ASSERTIONS = {
    "stop-once-per-job": "06-requested-execution.md",
    "conditional-project-hook-matchers": "06-requested-execution.md",
    "pre-push-interpreter-recovery": "05-requested-execution.md",
    "installer-runtime-selection": "06-requested-execution.md",
}


def runtime_command(command):
    """Recognize a completed executable call, not a source-read or echo claim.

    Harness names are unrestricted. The separate trace assertion checks their
    source and runtime calls; recognizing a Python command alone is insufficient.
    """
    if not isinstance(command, str):
        return False
    for words in _statements(_source(command)):
        words = words[1:] if words and words[0] == "&" else words
        if not words:
            continue
        executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if re.fullmatch(r"(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?", executable):
            arguments = words[1:]
            if any(flag in arguments for flag in ("--help", "-h", "--version", "-V")):
                continue
            if "-c" in arguments:
                try:
                    tree = ast.parse(arguments[arguments.index("-c") + 1])
                except (SyntaxError, IndexError):
                    continue
                # Literal JSON printing/replay is not an execution observation.
                if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and node.func.attr in {"run", "main", "dispatch", "call", "check_output"}
                       for node in ast.walk(tree)):
                    return True
            elif any(word.endswith(".py") for word in arguments) or "-m" in arguments:
                return True
        elif executable in {"sh", "bash", "cmd", "cmd.exe", "pwsh", "pwsh.exe", "powershell", "powershell.exe"}:
            if any(word.endswith((".sh", ".cmd", ".ps1")) for word in words[1:]):
                return True
        elif executable.endswith((".sh", ".cmd", ".ps1")):
            return True
    return False


def captured_json(ctx):
    """JSON emitted by successful commands, retained independently by the host."""
    decoder = json.JSONDecoder()
    for command in ctx.completed_commands:
        code = command.get("exit_code")
        if type(code) is not int or code != 0 or not runtime_command(command.get("command", "")):
            continue
        output = command.get("aggregated_output", "")
        if not isinstance(output, str):
            continue
        position = 0
        while position < len(output):
            match = re.search(r"[\[{]", output[position:])
            if not match:
                break
            position += match.start()
            try:
                value, end = decoder.raw_decode(output, position)
            except ValueError:
                position += 1
                continue
            yield value
            position = end


def observed_results(ctx, filename):
    result = ctx.data(filename)
    if not any(result == value for value in captured_json(ctx)):
        raise ValueError("No completed runtime invocation retains the reported response")
    return result


def runtime_evidence(ctx, case):
    """The trace judge cannot replace the independently captured observations."""
    try:
        if case == "stop-once-per-job":
            stop_reply(ctx, 0)
        else:
            filename = {"conditional-project-hook-matchers": "matcher-results.json",
                        "pre-push-interpreter-recovery": "recovery.json",
                        "installer-runtime-selection": "runtime-results.json"}[case]
            observed_results(ctx, filename)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        return False, f"Runtime invocation and response capture unavailable: {exc}"
    return True, "Successful command observations independently retain the reported runtime responses"


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: saved artifact predicate {passed}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False, f"{case}/{name}: missing or malformed artifact"
    CHECKS[case, name + ".md"] = check


register("plugin-shim-availability", "01-result", lambda c:
         all(arg in c.data("plugin-results.json")["installer_arguments"] for arg in ("--shim-only", "--home")))
register("plugin-shim-availability", "02-result", lambda c:
         bool(c.data("plugin-results.json")["settings_before"]) and
         c.data("plugin-results.json")["settings_before"] == c.data("plugin-results.json")["settings_after"])
register("plugin-shim-availability", "03-result", lambda c:
         type(c.data("plugin-results.json")["help_exit_code"]) is int and
         c.data("plugin-results.json")["help_exit_code"] == 0 and "brief" in c.data("plugin-results.json")["help_stdout"])
# The resolved command must be followed from a different directory, so this
# assertion is trace-reviewed rather than inferred from a matching prose claim.


def matcher_tools(ctx, name):
    tools = observed_results(ctx, "matcher-results.json")[name]
    if not isinstance(tools, list) or not tools or not all(isinstance(tool, str) for tool in tools):
        raise ValueError("tool array required")
    return set(tools)


register("conditional-project-hook-matchers", "01-inactive-tools", lambda c:
         {"AskUserQuestion", "Agent"} <= matcher_tools(c, "initial"))
register("conditional-project-hook-matchers", "02-reactivated-tools", lambda c:
         {"AskUserQuestion", "Agent"} <= matcher_tools(c, "refreshed"))
register("conditional-project-hook-matchers", "03-retained-protection", lambda c:
         all({"Bash", "PowerShell", "Edit", "Write", "NotebookEdit"} <= matcher_tools(c, name)
             for name in ("initial", "refreshed")))
register("conditional-project-hook-matchers", "04-generic-scope", lambda c:
         {"AskUserQuestion", "Agent"} <= matcher_tools(c, "plugin") and
         {"Bash", "PowerShell", "Edit", "Write", "NotebookEdit"} <= matcher_tools(c, "plugin"))


def measured_results(ctx):
    executed, evidence = ctx.execution("measure_posttool.py")
    if not executed:
        raise ValueError(evidence)
    return ctx.data("posttool-results.json")


def unchanged_counts(ctx, key):
    rows = measured_results(ctx)["unchanged"]
    return len(rows) == 2 and all(type(row[key]) is int and row[key] == 0
                                 and type(row["child_launches"]) is int and row["child_launches"] == 0
                                 and type(row["exit_code"]) is int and row["exit_code"] == 0 for row in rows)


register("posttool-unchanged-fast-path", "01-unchanged-body-reads", lambda c: unchanged_counts(c, "coordination_body_reads"))
register("posttool-unchanged-fast-path", "02-unchanged-dispatch", lambda c: unchanged_counts(c, "child_launches"))
register("posttool-unchanged-fast-path", "03-changed-record", lambda c:
         "records.id" in str(measured_results(c)["changed_record"]))
register("posttool-unchanged-fast-path", "04-pending-warning", lambda c:
         "pending operational warning" in str(measured_results(c)["pending_warning"]).lower())


COMMANDS = (
    "cd runs/owned && rm input.txt", "cd 'runs/owned' && printf ready && rm input.txt",
    "cd runs/sibling && rm input.txt", "cd $RUN_DIR && rm input.txt",
    "cd runs && cd owned && rm input.txt", "cd runs/owned && printf ready; rm input.txt",
    "printf ready && cd runs/owned",
)


def cd_rows(ctx):
    rows = ctx.data("cd-results.json")
    if not isinstance(rows, list) or [row["command"] for row in rows] != list(COMMANDS):
        raise ValueError("matrix incomplete or reordered")
    return rows


register("literal-cd-command-chain", "01-literal-bound", lambda c:
         all(row["decision"] == "block" and any(f["check"] == "jobs.mutate-bound" and f["certain"] is True
             for f in row["findings"]) for row in cd_rows(c)[:2]))
register("literal-cd-command-chain", "02-sibling-clear", lambda c:
         all(f["check"] != "jobs.mutate-bound" for f in cd_rows(c)[2]["findings"]))
register("literal-cd-command-chain", "03-uncertain-controls", lambda c:
         all(row["decision"] == "warn" and any(f["check"] == "jobs.mutate-bound" and f["certain"] is False
             for f in row["findings"]) for row in cd_rows(c)[3:6]))
register("literal-cd-command-chain", "04-trailing-only", lambda c:
         [any(f["check"] == "shell.cd" for f in row["findings"]) for row in cd_rows(c)] == [False] * 6 + [True])


def stop_reply(ctx, index):
    replies = ctx.data("stop-results.json")
    if not isinstance(replies, list) or len(replies) != 4 or not all(isinstance(reply, dict) for reply in replies):
        raise ValueError("four raw replies required")
    captured = list(captured_json(ctx))
    if replies not in captured:
        # Consume matches so a repeated reply still requires its own capture.
        for reply in replies:
            try:
                offset = captured.index(reply)
            except ValueError:
                raise ValueError("Four ordered independently captured Stop responses required") from None
            captured = captured[offset + 1:]
    return replies[index]


def warning_text(reply):
    return str(reply.get("systemMessage", "")) + str(reply.get("hookSpecificOutput", {}).get("additionalContext", ""))


register("stop-once-per-job", "01-first-job-blocks", lambda c:
         stop_reply(c, 0).get("decision") == "block" and "J-A-0001" in stop_reply(c, 0).get("reason", ""))
register("stop-once-per-job", "02-repeat-warns", lambda c:
         stop_reply(c, 1).get("decision") != "block" and "J-A-0001" in warning_text(stop_reply(c, 1)))
register("stop-once-per-job", "03-new-job-blocks", lambda c:
         stop_reply(c, 2).get("decision") == "block" and "J-A-0002" in stop_reply(c, 2).get("reason", "") and
         "J-A-0001" not in stop_reply(c, 2).get("reason", ""))
register("stop-once-per-job", "04-second-repeat-warns", lambda c:
         stop_reply(c, 3).get("decision") != "block" and all(job in warning_text(stop_reply(c, 3)) for job in ("J-A-0001", "J-A-0002")))


def retained_jobs(ctx):
    stop_reply(ctx, 0)
    jobs = ctx.data("project/.ro/jobs.json")
    if not isinstance(jobs, list) or len(jobs) != 2:
        return False
    return ({job["id"] for job in jobs} == {"J-A-0001", "J-A-0002"} and
            all(job.get("status") == "finished" and not (job.get("monitor") or {}).get("reason") for job in jobs))


register("stop-once-per-job", "05-retains-registry", retained_jobs)


register("pre-push-interpreter-recovery", "01-result", lambda c:
         bool(observed_results(c, "recovery.json")["override_command"]) and all(
             observed_results(c, "recovery.json")[name]["selected_command"] == command for name, command in
             (("override", observed_results(c, "recovery.json")["override_command"]), ("python3", ["python3"]),
              ("python", ["python"]), ("py", ["py", "-3"]))))
register("pre-push-interpreter-recovery", "02-result", lambda c:
         type(observed_results(c, "recovery.json")["unavailable"]["exit_code"]) is int and
         observed_results(c, "recovery.json")["unavailable"]["exit_code"] != 0 and
         all(token in observed_results(c, "recovery.json")["unavailable"]["stderr"] for token in ("Python 3.12+", "RO_HOOK_PYTHON")))
register("pre-push-interpreter-recovery", "03-result", lambda c:
         observed_results(c, "recovery.json")["denied"]["exit_code"] == 17 and
         len(observed_results(c, "recovery.json")["denied"]["scanner_calls"]) == 1)


def preserved_refs(ctx):
    data = observed_results(ctx, "recovery.json")
    if not data["remote"] or not bytes.fromhex(data["refs_hex"]).endswith(b"\r\n"):
        return False
    for name in ("override", "python3", "python", "py", "denied"):
        calls = data[name]["scanner_calls"]
        if not calls or any(call["stdin_hex"] != data["refs_hex"] or call["remote"] != data["remote"] for call in calls):
            return False
    return True


register("pre-push-interpreter-recovery", "04-result", preserved_refs)


def installed_runtime(ctx, scenario, host):
    data = observed_results(ctx, "runtime-results.json")[scenario]
    runtime = data["surviving_runtime"].replace("\\", "/")
    commands = "\n".join(line for line in data["shim_text"].splitlines()
                         if not re.match(r"\s*(?:#|rem\b)", line, re.I)).replace("\\", "/")
    return runtime.endswith(f"/{host}/skills/research-orchestrator/scripts/ro.py") and runtime in commands


def shim_help(ctx, scenario):
    code = observed_results(ctx, "runtime-results.json")[scenario]["shim_help_exit_code"]
    return type(code) is int and code == 0 and "Research Orchestrator" in ctx.text(scenario + "-help.txt")


case = "installer-runtime-selection"
register(case, "01-updated-cli", lambda c: installed_runtime(c, "upgrade", ".codex"))
register(case, "02-updated-gate", lambda c:
         observed_results(c, "runtime-results.json")["upgrade"]["pre_push_runtime"].replace("\\", "/") ==
         observed_results(c, "runtime-results.json")["upgrade"]["surviving_runtime"].replace("\\", "/") and
         installed_runtime(c, "upgrade", ".codex"))
register(case, "03-surviving-global", lambda c: installed_runtime(c, "fallback", ".claude"))
register(case, "04-upgrade-help", lambda c: shim_help(c, "upgrade"))
register(case, "05-fallback-help", lambda c: shim_help(c, "fallback"))

register("plugin-shim-availability", "05-no-copy", lambda c: c.data("plugin-results.json")["copied_skills"] == [])
register("plugin-shim-availability", "06-checkout-runtime", lambda c:
         c.data("plugin-results.json")["runtime_path"].replace("\\", "/").endswith(
             "/skills/research-orchestrator/scripts/ro.py") and
         not any(part in c.data("plugin-results.json")["runtime_path"].replace("\\", "/")
                 for part in ("/.claude/skills/", "/.codex/skills/", "/.agents/skills/")))
