"""Detect visible executor access to material outside its assigned evaluation.

The sandbox is not a read jail. This audit keeps attempted access as findings;
source repository contamination requires a completed read of an existing file.
Prompt/final-message prose is never treated as file access.
It cannot prove that an opaque program did not compute or conceal another path.
"""
from __future__ import annotations

import ast
import io
import json
import ntpath
from pathlib import Path, PurePosixPath
import posixpath
import re
import tokenize

try:
    from .command_trace import _source, _statements
except ImportError:
    from command_trace import _source, _statements


def _resolved(path: str, cwd: str = "") -> str:
    path = path.strip().replace("\\", "/")
    if path.startswith("file://"):
        path = path[7:]
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
    windows = bool(re.match(r"^[A-Za-z]:", path) or re.match(r"^[A-Za-z]:", cwd))
    module = ntpath if windows else posixpath
    if cwd and not module.isabs(path):
        path = module.join(cwd, path)
    return module.normpath(path).replace("\\", "/")


def _normal(path: str, cwd: str = "") -> str:
    return _resolved(path, cwd).casefold().rstrip("/")


def _within(path: str, root: str) -> bool:
    parts, root_parts = PurePosixPath(path).parts, PurePosixPath(root).parts
    return bool(root) and parts[:len(root_parts)] == root_parts


def _allowed_roots(run_dir: Path, project: Path | None, runtime: Path | None) -> list[str]:
    return [_normal(str(path)) for path in (project.parent if project else None,
                                           project, runtime, run_dir / "evidence") if path]


def _eval_or_grader_path(path: str, allowed: list[str]) -> bool:
    # A workspace may itself be named evals. Only names below the assigned
    # staging boundary identify hidden evaluation material in an allowed tree.
    # Keep checking those descendants: allowing a runtime does not allow its graders.
    roots = [root for root in allowed if _within(path, root)]
    relative = path[len(max(roots, key=len)):].lstrip("/") if roots else path
    return bool({"evals", "graders"}.intersection(relative.split("/")))


def _path_reason(path: str, *, source: str, work: str, own_run: str, allowed: list[str],
                 baseline: list[str], installed: list[str], global_agents: str) -> str | None:
    if any(_within(path, root) for root in installed):
        return "installed_skill"
    if global_agents and path == global_agents:
        return "global_agents"
    if _eval_or_grader_path(path, allowed):
        return "eval_or_grader_path"
    if any(_within(path, root) for root in allowed):
        return None
    if _within(path, source):
        return "source_repository"
    if any(_within(path, root) for root in baseline):
        return "baseline_snapshot"
    if _within(path, work) and not _within(path, own_run):
        return "other_workspace_run"
    return None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _operations(event: dict, inherited_cwd=None, completed=False):
    """Accept CLI command/file events and structured tool-call representations."""
    kind = event.get("type", "")
    if kind in {"agent_message", "message", "reasoning", "user_message"}:
        return
    cwd = event.get("cwd") or event.get("workdir") or event.get("working_directory") or inherited_cwd
    completed |= kind in {"item.completed", "tool.completed"}
    outcome = {**event, "completed": completed}
    if kind in {"command_execution", "shell_command"}:
        yield kind, event.get("command", ""), cwd, outcome
        return
    if kind in {"file_change", "file_read", "file_access", "file_open", "read_file", "file_write"}:
        paths = [event[key] for key in ("path", "file_path", "filename", "paths") if key in event]
        # Changes may include source text; only the file name is access evidence.
        if kind == "file_change":
            paths.extend(change.get("path", "") for change in event.get("changes", []) if isinstance(change, dict))
        yield kind, paths, cwd, outcome
        return
    if kind in {"function_call", "tool_call", "tool_use", "mcp_tool_call", "custom_tool_call"}:
        if isinstance(event.get("function"), dict):
            yield from _operations({"type": "function_call", **event["function"]}, cwd, completed)
            return
        value = event.get("arguments", event.get("input", event.get("parameters", {})))
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        if isinstance(value, dict):
            cwd = value.get("cwd", value.get("workdir", value.get("working_directory", cwd)))
        name = str(event.get("name", event.get("tool", kind)))
        if isinstance(value, dict) and re.search(
                r"(?:^|[._:/])(?:read|write|edit|read_file|write_file|edit_file|create_file)$", name.casefold()):
            # New file contents and replacement text are prose, not extra reads.
            value = {key: value[key] for key in ("path", "file_path", "filename", "paths") if key in value}
        yield name, value, cwd, outcome
        return
    for key in ("item", "payload", "tool_call", "function"):
        if isinstance(event.get(key), dict):
            yield from _operations(event[key], cwd, completed)


def _events(run_dir: Path):
    events = run_dir / "events.jsonl"
    if events.is_file():
        for number, line in enumerate(events.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                yield f"events.jsonl:{number}", data
    transcript = run_dir / "transcript.md"
    if transcript.is_file():
        text = transcript.read_text(encoding="utf-8", errors="replace")
        # The runner embeds each event under its own heading. Never scan the
        # prompt, agent prose, or final message for alleged access.
        for match in re.finditer(r"(?m)^## Event ([^\n]+)\n([\s\S]*?)(?=^## |\Z)", text):
            for block in re.findall(r"```json\s*\n([\s\S]*?)\n```", match[2]):
                try:
                    data = json.loads(block)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    yield "transcript.md:Event " + match[1], data


def _literal_path_parts(text: str) -> list[str]:
    # The shell lexer removes quotes from PowerShell arrays and Python raw
    # strings. Restore their literal operands instead of inventing a path that
    # embeds a second drive letter beneath the current project.
    pieces = text.rstrip(",").split(",")
    if "," in text and all(re.match(r"^[A-Za-z]:[/\\]", piece) for piece in pieces):
        return pieces
    if re.match(r"^[rR][A-Za-z]:[/\\]", text):
        return [text[1:]]
    return [text]


def _paths(text: str):
    # Preserve quoted paths with spaces, while also inspecting shell/Python
    # expressions embedded in a command argument. No shell is executed here.
    candidates = [text, *re.findall(r'''["']([^"'\r\n]+)["']''', text),
                  *re.findall(r'''[^\s"'`;,(){}\[\]<>|=]+''', text)]
    for candidate in candidates:
        yield from _literal_path_parts(candidate)


def _python_here_strings(command: str):
    """Extract literal Python stdin bodies without evaluating PowerShell."""
    return re.finditer(
        r"(?ms)^\s*@(['\"])\r?\n(.*?)^\1@\s*\|\s*&?\s*['\"]?[^\r\n]*\b(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?['\"]?(?:\s+-(?:B|u|3))*\s*(?:-\s*)?$",
        _source(command))


def _inert_python_paths(command: str) -> set[str]:
    """Identify comments and literal comparison/replacement/output data, not paths.

    A literal used elsewhere in the program remains subject to the audit, so
    adding a harmless comparison cannot hide the same operand in a read call.
    """
    inert, other = set(), set()
    for program in _python_here_strings(command):
        try:
            tree = ast.parse(program[2])
            comments = [token.string for token in tokenize.generate_tokens(io.StringIO(program[2]).readline)
                        if token.type == tokenize.COMMENT]
        except (SyntaxError, ValueError, tokenize.TokenError):
            continue
        data_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                data_nodes.update([node.left, *node.comparators])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                data_nodes.update(node.args)
                for argument in node.args:
                    if isinstance(argument, ast.JoinedStr):
                        data_nodes.update(part for part in argument.values if isinstance(part, ast.Constant))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil"
                  and node.func.attr == "ignore_patterns"):
                data_nodes.update(node.args)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "replace" and len(node.args) in {2, 3}
                  and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args[:2])):
                data_nodes.update(node.args[:2])
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                (inert if node in data_nodes else other).update(_paths(node.value))
        for comment in comments:
            inert.update(_paths(comment))
    return inert - other


def _code_fragment(candidate: str, inputs, value) -> bool:
    # A shell argument can be an entire Python program or here-string. Its
    # embedded literals are checked separately by _paths; resolving the program
    # itself below cwd invents a second path containing the workspace's name.
    command = value if isinstance(value, str) else value.get("cmd", value.get("command", "")) if isinstance(value, dict) else ""
    if not isinstance(inputs, list):
        # If shell quoting cannot be parsed, the fallback still extracts every
        # embedded literal. The entire shell command itself is not a filename.
        return isinstance(inputs, str) and inputs == command and candidate == inputs
    words = inputs[1:] if inputs and inputs[0] == "&" else inputs
    if words and words[0].casefold() == "where-object":
        # A filename predicate filters a directory listing; it is not a request
        # to open the compared filename. A later read is a separate statement.
        if any(words[index - 1].casefold() == "$_.name" and word.casefold() in {"-eq", "-ne"}
               and index + 1 < len(words) and candidate == words[index + 1]
               for index, word in enumerate(words) if index):
            return True
    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe") if words else ""
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?|py", executable) and "-c" in words:
        index = words.index("-c") + 1
        if index < len(words) and candidate == words[index]:
            return True
    # shlex strips the nested quotes from a PowerShell here-string; a multiline
    # token from that source is code, while its separately extracted paths are not.
    if not isinstance(command, str) or not next(_python_here_strings(command), None):
        return False
    if words and re.match(r"^@\r?\n", words[0]):
        if candidate in words and "\n" in candidate:
            return True
    if candidate in _inert_python_paths(command):
        # Nested quotes can make the shell lexer split one stdin program into
        # several apparent statements. Match only tokens from the program, so
        # a real command following its closing marker retains its own operands.
        return any(words == statement for program in _python_here_strings(command)
                   for statement in _statements(f"@{program[1]}\n{program[2]}{program[1]}@"))
    return False


def _ancestor_instruction_probe(path: str, inputs, project: Path | None,
                                value, outcome: dict, *, literal: str = "", cwd: str = "") -> str | None:
    """Recognize a bounded, guarded search for absent ancestor instructions.

    Only array assignments in the familiar Test-Path/Get-Content loop qualify.
    Directory listings, direct reads, and other workspace files stay subject to
    the normal audit. Native output and current existence both veto recovery.
    """
    if (project is None or not isinstance(inputs, list) or len(inputs) < 3
            or not re.fullmatch(r"\$\w+", inputs[0]) or inputs[1] != "=" or "@" not in inputs):
        return None
    command = value if isinstance(value, str) else value.get("cmd", value.get("command", "")) if isinstance(value, dict) else ""
    if not isinstance(command, str):
        return None
    source = _source(command)
    # A comma outside quotes separates PowerShell array operands. shlex keeps
    # it on a relative path token, so normalize the literal before resolving
    # `..`; stripping it from the already resolved path would lose a parent.
    # Require the original quote boundary to preserve filenames ending in a comma.
    if literal.endswith(",") and any(
            match[2] == literal[:-1] for match in re.finditer(r"(['\"])([^'\"\r\n]+)\1\s*,", source)):
        path = _resolved(literal[:-1], cwd)
    loop = re.search(r"\bforeach\s*\(\s*(\$\w+)\s+in\s+" + re.escape(inputs[0]) + r"\s*\)", source, re.I)
    guarded = re.search(r"\bif\s*\(\s*Test-Path\s+(?:-LiteralPath\s+|-Path\s+)?(\$\w+)\s*\)", source, re.I)
    if not loop or not guarded:
        return None
    content_reads = re.findall(r"\bGet-Content\s+(?:-[\w]+\s+)*" + re.escape(guarded[1]) + r"\b", source, re.I)
    if len(content_reads) != 1:
        return None
    root = PurePosixPath(_normal(str(project)))
    ancestors = {str(parent) for parent in root.parents}
    target = PurePosixPath(_normal(path))
    if (target.name == "agents.md" and str(target.parent) in ancestors
            and guarded[1].casefold() == loop[1].casefold()):
        instruction = path
    elif _normal(path) in ancestors and re.search(
            re.escape(guarded[1]) + r"\s*=\s*Join-Path\s+" + re.escape(loop[1]) + r"\s+['\"]AGENTS\.md['\"]", source, re.I):
        instruction = path + "/AGENTS.md"
    else:
        return None
    try:
        if Path(instruction).exists():
            return None
    except OSError:
        return None
    if (outcome.get("status") == "in_progress" or not outcome.get("completed")) and outcome.get("exit_code") is None:
        return "unconfirmed_ancestor_probe"
    if "aggregated_output" not in outcome and "output" not in outcome:
        return None
    output = str(outcome.get("aggregated_output", outcome.get("output", ""))).replace("\\", "/").casefold()
    if _normal(instruction) in output or "get-content" in output or outcome.get("error"):
        return None
    if output.strip():
        # A combined native event can append argparse help after the probe.
        # Accept only its recognizable help output and a loop that would print
        # the full filename before any contents; a deleted file's bare contents
        # cannot then be mistaken for an absent probe.
        announced = re.search(r"\bGet-Item\s+-LiteralPath\s+" + re.escape(guarded[1])
                              + r"\s*\|\s*Select-Object\s+FullName\s*;\s*Get-Content", source, re.I)
        if not (announced and source.rstrip().endswith("--help")
                and output.lstrip().startswith("usage: ") and "options:" in output):
            return None
    if outcome.get("exit_code") == 0:
        return "absent_ancestor_instructions"
    if outcome.get("status") == "in_progress" or not outcome.get("completed"):
        return "unconfirmed_ancestor_probe"
    return None


def _host_path(path: str, host_context: dict) -> str:
    """Expand common home spellings using the executor's recorded environment."""
    path = path.replace("\\", "/")
    # PowerShell's automatic $HOME exists even when the HOME environment variable does not.
    home = host_context.get("user_home")
    homes = {"~": home, "$HOME": home, "${HOME}": home}
    variables = {**host_context.get("home_variables", {}), "CODEX_HOME": host_context.get("codex_home")}
    for name, value in variables.items():
        for prefix in (f"${name}", "${" + name + "}", f"$env:{name}", "${env:" + name + "}", f"%{name}%"):
            homes[prefix] = value
    for prefix, value in homes.items():
        if value and (path.casefold() == prefix.casefold() or path.casefold().startswith(prefix.casefold() + "/")):
            return value + path[len(prefix):]
    return path


def _access_contexts(operation: str, value, cwd: str, host_context: dict):
    """Resolve literal shell directory changes without executing shell code."""
    command = value if operation in {"command_execution", "shell_command"} else None
    if isinstance(value, dict):
        command = value.get("cmd", value.get("command"))
    if not isinstance(command, str):
        reading = bool(re.search(r"(?:^|[._:/])(?:read|read_file|file_read|file_open|file_access)$",
                                 operation.casefold()))
        yield value, cwd, reading
        return
    programs = {}
    for program in _python_here_strings(command):
        first = next(_statements(f"@{program[1]}\n{program[2]}{program[1]}@"), [])
        if first:
            programs[tuple(first)] = program[2]
    statements = list(_statements(_source(command)))
    if not statements:
        yield command, cwd, False
        return
    stack = []
    for words in statements:
        if words and words[0] == "&":
            words = words[1:]
        if not words:
            continue
        executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")
        if executable in {"cd", "chdir", "set-location", "sl", "pushd", "push-location"}:
            previous_cwd = cwd
            arguments = [word for word in words[1:] if word.casefold() not in {"-literalpath", "-path", "/d"}]
            target = _host_path(arguments[0], host_context) if len(arguments) == 1 else ""
            if target and not target.startswith("$"):
                if executable in {"pushd", "push-location"}:
                    stack.append(cwd)
                cwd = _resolved(target, cwd)
            yield words[1:], previous_cwd, False
            continue
        if executable in {"popd", "pop-location"} and stack:
            cwd = stack.pop()
            continue
        if tuple(words) in programs:
            # Apply prior directory changes to actual literal reads in stdin.
            # The body remains code, while its read operands establish access.
            yield _python_reads(["-c", programs[tuple(words)]]), cwd, True
        readers = {"get-content", "gc", "cat", "type", "more", "less", "head", "tail", "sed", "rg", "grep", "awk"}
        reading = executable in readers
        if any(word.casefold() in {"--help", "-h", "-?", "--version", "--files"} for word in words[1:]):
            reading = False
        yield words, cwd, reading
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?|py", executable):
            yield _python_reads(words[1:]), cwd, True


def _python_reads(arguments: list[str]) -> list[str]:
    """Recognize literal script/read operands, never execute or infer Python."""
    while arguments and arguments[0] in {"-u", "-B", "-3"}:
        arguments = arguments[1:]
    if not arguments:
        return []
    if arguments[0] != "-c":
        return [arguments[0]] if not arguments[0].startswith("-") else []
    if len(arguments) < 2:
        return []
    try:
        tree = ast.parse(arguments[1])
    except (SyntaxError, ValueError):
        return []
    paths = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = None
        if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
            mode = next((kw.value for kw in node.keywords if kw.arg == "mode"),
                        node.args[1] if len(node.args) > 1 else ast.Constant("r"))
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and ("r" in mode.value or "+" in mode.value):
                target = node.args[0]
        elif (isinstance(node.func, ast.Attribute) and node.func.attr in {"read_text", "read_bytes"}
              and isinstance(node.func.value, ast.Call)):
            constructor = node.func.value
            name = constructor.func.id if isinstance(constructor.func, ast.Name) else ""
            if name == "Path" and constructor.args:
                target = constructor.args[0]
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            paths.append(target.value)
    return paths


def _source_access(outcome: dict, path: str, reading: bool) -> tuple[bool, str]:
    """A started/failed command or a guessed missing path is only an attempt."""
    failed = (outcome.get("error") or outcome.get("success") is False
              or outcome.get("status") in {"failed", "in_progress", "cancelled"}
              or outcome.get("exit_code") not in {None, 0})
    if failed:
        return False, "failed" if outcome.get("status") != "in_progress" else "unconfirmed"
    successful = (outcome.get("exit_code") == 0 if outcome.get("type") in {"command_execution", "shell_command"}
                  else outcome.get("success") is True or outcome.get("status") == "completed" or outcome.get("completed"))
    if not successful:
        return False, "unconfirmed"
    if not reading:
        return False, "not_a_read"
    try:
        real_file = Path(path).is_file()
    except (OSError, ValueError):
        real_file = False
    return (True, "successful_read") if real_file else (False, "not_a_file")


def audit_run(run_dir: Path, *, source_repo: Path, workspace: Path,
              project: Path | None, runtime: Path | None, baseline_roots=(), host_context: dict | None = None,
              _observed_accesses: set | None = None) -> dict:
    """Return serializable findings and enough policy to audit saved runs again."""
    baseline_roots = tuple(baseline_roots)
    host_context = host_context or {}
    policy = {"source_repo": str(source_repo), "workspace": str(workspace),
              "project": str(project) if project else None, "runtime": str(runtime) if runtime else None,
              "baseline_roots": [str(path) for path in baseline_roots], "host_context": host_context}
    source = _normal(str(source_repo))
    work = _normal(str(workspace))
    own_run = _normal(str(run_dir))
    # Broker clients read only their own protected receipts. This exception must
    # also work when the workspace itself is nested in the source checkout.
    allowed = _allowed_roots(run_dir, project, runtime)
    baseline = [_normal(str(path)) for path in baseline_roots]
    baseline.append(_normal(str(workspace / "old-skill-snapshot")))
    installed = [_normal(path) for path in host_context.get("installed_skill_roots", [])]
    agents = host_context.get("global_agents", {})
    global_agents = _normal(agents["path"]) if agents.get("size_bytes") and agents.get("path") else ""
    default_cwd = str(project) if project else ""
    findings = []
    seen = {}
    operations = 0
    for location, event in _events(run_dir):
        for operation, value, cwd, outcome in _operations(event):
            operations += 1
            cwd = _resolved(_host_path(cwd, host_context), default_cwd) if isinstance(cwd, str) else default_cwd
            for inputs, command_cwd, reading in _access_contexts(operation, value, cwd, host_context):
                for candidate in (path for text in _strings(inputs) for path in _paths(text)):
                    candidate = candidate.strip()
                    if not candidate or ("/" not in candidate and "\\" not in candidate
                                         and candidate.casefold() not in {"evals", "graders", ".", ".."}
                                         and not re.fullmatch(r"[\w.-]+\.[\w.-]+", candidate)):
                        continue
                    resolved = _resolved(_host_path(candidate, host_context), command_cwd)
                    path = _normal(resolved)
                    if _observed_accesses is not None:
                        _observed_accesses.add((operation, path))
                    reason = _path_reason(path, source=source, work=work, own_run=own_run, allowed=allowed,
                                          baseline=baseline, installed=installed, global_agents=global_agents)
                    if reason is None:
                        continue
                    probe = (_ancestor_instruction_probe(resolved, inputs, project, value, outcome,
                                                         literal=candidate, cwd=command_cwd)
                             if reason in {"eval_or_grader_path", "other_workspace_run"} else None)
                    if _code_fragment(candidate, inputs, value):
                        contaminating, access_outcome = False, "code_not_path"
                    elif probe:
                        contaminating, access_outcome = False, probe
                    else:
                        contaminating, access_outcome = (_source_access(outcome, resolved, reading)
                                                         if reason == "source_repository" else (True, "attempted_access"))
                    key = (operation, path, reason)
                    finding = {"reason": reason, "path": candidate, "resolved_path": resolved,
                               "operation": operation, "evidence": location,
                               "contaminating": contaminating, "outcome": access_outcome}
                    if key not in seen:
                        seen[key] = len(findings)
                        findings.append(finding)
                    elif contaminating or (not findings[seen[key]]["contaminating"]
                                           and access_outcome != "unconfirmed"):
                        # Completed events supersede item.started; a later failure
                        # must never erase an earlier successful read.
                        findings[seen[key]] = finding
    return {"contaminated": any(finding["contaminating"] for finding in findings),
            "findings": findings, "policy": policy,
            "operations_checked": operations,
            "limitation": "Audits visible commands and file/tool access; concealed or unreported reads cannot be ruled out."}


def is_contaminated(run: dict) -> bool:
    report = run.get("contamination")
    return bool(run.get("contaminated") or run.get("status") == "contaminated"
                or (isinstance(report, dict) and report.get("contaminated")))


def audit_saved_run(run_dir: Path, run: dict) -> dict:
    """Retain flags except reproduced boundary, code-operand, and absent-probe mistakes."""
    previous = run.get("contamination") or {}
    if not isinstance(previous, dict):
        raise ValueError("Invalid contamination audit metadata")
    policy = previous.get("policy")
    if not isinstance(policy, dict):
        return {**previous, "contaminated": is_contaminated(run)}
    project = Path(policy["project"]) if policy.get("project") else None
    runtime = Path(policy["runtime"]) if policy.get("runtime") else None
    observed = set()
    report = audit_run(run_dir, source_repo=Path(policy["source_repo"]), workspace=Path(policy["workspace"]),
                       project=project, runtime=runtime,
                       baseline_roots=[Path(path) for path in policy.get("baseline_roots", [])],
                       host_context=policy.get("host_context"), _observed_accesses=observed)
    if is_contaminated(run) and not report["contaminated"]:
        allowed = _allowed_roots(run_dir, project, runtime)
        host = policy.get("host_context", {})
        agents = host.get("global_agents", {})
        classifier = {"source": _normal(policy["source_repo"]), "work": _normal(policy["workspace"]),
                      "own_run": _normal(str(run_dir)), "allowed": allowed,
                      "baseline": [_normal(path) for path in policy.get("baseline_roots", [])]
                                  + [_normal(str(Path(policy["workspace"]) / "old-skill-snapshot"))],
                      "installed": [_normal(path) for path in host.get("installed_skill_roots", [])],
                      "global_agents": _normal(agents["path"]) if agents.get("path") and agents.get("size_bytes") else ""}
        old_findings = previous.get("findings", [])
        positive = [finding for finding in old_findings if finding.get("contaminating", True)]
        disproved = {(finding["operation"], _normal(finding["resolved_path"]))
                     for finding in report["findings"] if not finding["contaminating"]
                     and finding["outcome"] in {"code_not_path", "absent_ancestor_instructions"}}
        reclassified = []
        for finding in positive:
            original = finding.get("path", "")
            literals = _literal_path_parts(original)
            paths = ([_normal(path) for path in literals] if literals != [original]
                     else [_normal(finding.get("resolved_path", ""))])
            if (finding.get("reason") == "eval_or_grader_path"
                    and _eval_or_grader_path(_normal(finding.get("resolved_path", "")), [])
                    and all((finding.get("operation"), path) in observed
                            and (_path_reason(path, **classifier) is None
                                 or (finding.get("operation"), path) in disproved)
                            for path in paths)):
                reclassified.append(finding)
        if positive and len(reclassified) == len(positive):
            report["reclassified_previous_contamination"] = True
            report["reclassified_findings"] = reclassified
        else:
            # A missing trace, runtime integrity failure, or another original
            # finding cannot be cleared merely because today's audit is clean.
            report["contaminated"] = True
            report["findings"] = old_findings
    return report


CONTAMINATION_EXCLUSION_REASON = "Contaminated executor trace; excluded from grading and benchmark statistics"


def recover_reclassified_run(run: dict, report: dict) -> bool:
    """Restore executor state only for the narrowly proven audit correction."""
    if report.get("contaminated") or not report.get("reclassified_previous_contamination"):
        return False
    run.update(contaminated=False, contamination=report)
    if run.get("status") == "contaminated":
        run["status"] = run.get("executor_status") or (
            "completed" if run.get("returncode") == 0 and not run.get("error") else "failed")
    if run.get("exclusion_reason") == CONTAMINATION_EXCLUSION_REASON:
        run.pop("excluded", None)
        run.pop("exclusion_reason", None)
    return True
