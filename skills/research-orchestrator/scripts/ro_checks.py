"""Small declared-environment checks shared by commands and hook adapters."""

from __future__ import annotations

from collections import namedtuple
import fnmatch
import ntpath
import os
from pathlib import Path
import posixpath
import re

import ro_settings as settings


# Named tuples and small classes, not dataclasses: importing dataclasses costs ~15 ms per hook call.
Finding = namedtuple("Finding", "check message uncertain identity", defaults=(False, ()))


class Call:
    """One normalized host tool call."""

    __slots__ = ("tool", "dialect", "command", "paths", "background", "agent_type", "prompt")

    def __init__(self, tool: str = "", dialect: str = "bash", command: str = "", paths: list[str] | None = None,
                 background: bool = False, agent_type: str = "", prompt: str = ""):
        self.tool, self.dialect, self.command = tool, dialect, command
        self.paths = paths if paths is not None else []
        self.background, self.agent_type, self.prompt = background, agent_type, prompt

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Call) and all(getattr(self, k) == getattr(other, k) for k in self.__slots__)

    def __repr__(self) -> str:
        return "Call(" + ", ".join(f"{k}={getattr(self, k)!r}" for k in self.__slots__) + ")"


def adapt(payload: dict) -> Call:
    """Normalize actual host fields; never execute JSON, recorded commands or patch text."""
    name = payload.get("tool_name", payload.get("tool", ""))
    raw = payload.get("tool_input", payload.get("input", {}))
    if isinstance(raw, str):
        raw = {"patch": raw} if name == "apply_patch" else {"command": raw}
    if not isinstance(raw, dict) or not isinstance(name, str):
        raise ValueError("invalid tool input")
    command = raw.get("command", raw.get("cmd", ""))
    if isinstance(command, list):
        if not all(isinstance(part, str) and "\0" not in part for part in command):
            raise ValueError("command argv must contain text")
        # Codex shell sometimes supplies [shell, -c, body]. Only the outer dialect is inferred.
        executable = command[0].lower().replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe") if command else ""
        if (len(command) >= 3 and executable in ("bash", "zsh", "sh", "powershell", "pwsh")
                and command[-2].lower() in ("-c", "-lc", "-command")):
            raw = {**raw, "shell": command[0]}
            command = command[-1]
        else:
            # Literal argv elements are data, not shell operators.
            import shlex
            command = shlex.join(command)
    if not isinstance(command, str):
        raise ValueError("command must be text")
    shell = str(raw.get("shell", payload.get("shell", ""))).lower().replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")
    dialect = ("powershell" if name.lower() == "powershell" or shell in ("powershell", "pwsh")
               else "bash" if name == "Bash" or shell in ("", "bash", "zsh", "sh") else "other")
    tool = "shell" if name in ("Bash", "PowerShell", "shell", "exec_command") else name
    paths = [str(raw[key]) for key in ("file_path", "path", "notebook_path") if raw.get(key)]
    if name == "apply_patch":
        tool = "Edit"
        patch = str(raw.get("patch", raw.get("input", "")))
        paths += re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", patch, re.M)
    return Call(tool, dialect, command, paths,
                bool(raw.get("run_in_background") or raw.get("background") or payload.get("background")),
                str(raw.get("subagent_type", raw.get("agent_type", ""))), str(raw.get("prompt", "")))


def normal_path(value: str, root: Path | str, os_family: str | None = None) -> str | None:
    """Compare literal components using only the declared OS; no path translation."""
    os_family = os_family or settings.detect_environment().split("/")[0]
    value = value.strip().strip("\"'")
    # Only a leading tilde expands to a home folder; one inside a component is literal,
    # as in Windows 8.3 short names (C:\Users\RUNNER~1) that temp folders often use.
    if not value or value.startswith("~") or re.search(r"[$`*?\[]|%[^%]+%", value):
        return None
    if os_family == "windows":
        # Rooted paths without a drive, drive-relative paths and UNC are outside this grammar.
        if (value.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:(?![/\\])", value)):
            return None
        return ntpath.normcase(ntpath.normpath(ntpath.join(str(root), value))).replace("\\", "/").rstrip("/")
    return posixpath.normpath(posixpath.join(str(root), value))


def inside(path: str, bound: str) -> bool:
    return path == bound or path.startswith(bound.rstrip("/") + "/")


def path_forms(path: str, os_family: str) -> set[str]:
    """The lexical path plus, on this machine's own OS, its resolved form.

    One folder can have two spellings: Windows 8.3 short names (RUNNER~1) and macOS
    /var -> /private/var. A job binding written with one spelling must still match a
    command that reaches the same folder through the other.
    """
    forms = {path}
    if (os_family == "windows") != (os.name == "nt"):
        return forms
    try:
        real = os.path.realpath(path)
    except (OSError, ValueError):
        return forms
    if os_family == "windows":
        forms.add(ntpath.normcase(ntpath.normpath(real)).replace("\\", "/").rstrip("/"))
    else:
        forms.add(posixpath.normpath(real))
    return forms


def overlaps(path: str, bound: str, os_family: str, ancestor: bool = False) -> bool:
    paths, bounds = path_forms(path, os_family), path_forms(bound, os_family)
    return any(inside(p, b) or (ancestor and inside(b, p)) for p in paths for b in bounds)


Token = namedtuple("Token", "value depth quoted start end", defaults=(False, -1, -1))


class ShellParse:
    """Lexical evidence and command-wide uncertainty shared by every shell check."""

    __slots__ = ("parts", "bodies", "uncertain")

    def __init__(self, parts: list[Token] | None = None, bodies: list[tuple[str, str, bool]] | None = None,
                 uncertain: bool = False):
        self.parts = parts if parts is not None else []
        self.bodies = bodies if bodies is not None else []
        self.uncertain = uncertain


def heredocs(command: str, parsed: ShellParse) -> str:
    """Mask bodies before shell lexing. Quoting the delimiter disables expansion."""
    lines = command.splitlines(keepends=True)
    output = []
    index = 0
    while index < len(lines):
        header = lines[index]
        output.append(header)
        index += 1
        starts = {t.start for t in tokens(header, "bash").parts if not t.quoted and t.value in ("<<", "<<-")}
        matched = set()
        for match in re.finditer(r"(?<!<)<<(-)?(?!<)\s*((?:\\.|'[^']*'|\"[^\"]*\"|[A-Za-z0-9_-])+)", header):
            if match.start() not in starts:
                continue
            matched.add(match.start())
            import shlex
            delimiter = shlex.split(match[2])[0]
            quoted = any(char in match[2] for char in "'\"\\")
            body = []
            while index < len(lines):
                line = lines[index]
                index += 1
                end = line.rstrip("\r\n")
                if match[1]:
                    end = end.lstrip("\t")
                output.append(" " * len(line.rstrip("\r\n")) + ("\n" if line.endswith("\n") else ""))
                if end == delimiter:
                    break
                body.append(line)
            else:
                parsed.uncertain = True
            parsed.bodies.append((header, "".join(body), quoted))
        parsed.uncertain |= starts != matched
    return "".join(output)


def here_string_end(command: str, index: int, parsed: ShellParse) -> int | None:
    if not re.compile(r'''@["'][ \t]*\r?\n''').match(command, index):
        return None
    terminator = re.compile(r"(?m)^" + re.escape(command[index + 1] + "@")).search(command, index + 2)
    parsed.uncertain |= terminator is None
    return terminator.end() if terminator else len(command)


def comment_end(command: str, index: int, parsed: ShellParse) -> int:
    end = command.find("#>", index + 2)
    parsed.uncertain |= end < 0 or "<#" in command[index + 2:end]
    return len(command) if end < 0 else end + 2


def substitution_end(command: str, index: int, dialect: str, parsed: ShellParse, opening: str = "$(") -> int:
    level, end, quote = 1, index + len(opening), ""
    data = dialect == "bash" and (opening == "{" or command.startswith(("((", "$((", "[["), index))
    opening = opening[-1]
    closing = {"(": ")", "{": "}", "[": "]"}[opening]
    while end < len(command) and level:
        char = command[end]
        if quote != "'" and ((char == "\\" and dialect == "bash") or (char == "`" and dialect == "powershell")):
            parsed.uncertain |= end + 1 == len(command)
            end += 2
            continue
        if quote:
            if char == quote:
                if dialect == "powershell" and command[end:end + 2] == quote * 2:
                    end += 2
                    continue
                quote = ""
            elif quote == '"' and command.startswith("$(", end):
                end = substitution_end(command, end, dialect, parsed)
                continue
            elif quote == '"' and char == "`" and dialect == "bash":
                parsed.uncertain = True  # Nested backtick quoting is outside the boundary grammar.
        elif char in "'\"" or (char == "`" and dialect == "bash"):
            quote = char
        elif dialect == "powershell" and command.startswith("<#", end):
            # Mask comments before counting braces; broken boundaries set uncertainty.
            end = comment_end(command, end, parsed)
            continue
        elif dialect == "powershell" and char == "@" and (data_end := here_string_end(command, end, parsed)) is not None:
            end = data_end
            continue
        elif command.startswith("$(", end):
            end = substitution_end(command, end, dialect, parsed)
            continue
        elif char in "({" and char != opening and opening != "[":
            end = substitution_end(command, end, dialect, parsed, char)
            continue
        elif char in ")}" and char != closing and opening != "[":
            parsed.uncertain = True
        elif char == "#" and not data:
            newline = command.find("\n", end)
            end = len(command) if newline < 0 else newline
            continue
        elif dialect == "bash" and not data and command.startswith(("<<", "<(", ">("), end):
            parsed.uncertain = True  # Nested redirection bodies are outside the boundary grammar.
        elif opening == "[" and command.startswith("]]", end):
            # Conditional patterns may contain individual brackets; only a closing word ends the body.
            before = command[end - 1]
            after = command[end + 2:end + 3]
            if (before.isspace() or before in "&|()") and (not after or after.isspace() or after in "&;|()<>"):
                return end + 2
        elif char == opening and opening != "[":
            level += 1
        elif char == closing and opening != "[":
            level -= 1
        end += 1
    parsed.uncertain |= bool(level or quote)
    return min(end, len(command))


def tokens(command: str, dialect: str, parsed: ShellParse | None = None, *, grouping: bool = False) -> ShellParse:
    """Small lexical grammar: preserve literal words; opaque quotes and substitutions aren't operators."""
    parsed = parsed if parsed is not None else ShellParse()
    result, word = parsed.parts, []
    index, depth, quoted, word_start = 0, 0, False, 0

    def command_position() -> bool:
        if not result or (not result[-1].quoted and result[-1].value in SEPARATORS | {"("}):
            return True
        return dialect == "bash" and not verb(statements(result)[-1])[0]

    def flush() -> None:
        nonlocal quoted
        if word:
            result.append(Token("".join(word), depth, quoted, word_start, index))
            word.clear()
        quoted = False

    while index < len(command):
        char = command[index]
        if not word:
            word_start = index
        if dialect == "powershell" and command.startswith("<#", index):
            flush()
            index = comment_end(command, index, parsed)
            continue
        if char == "#" and not word:
            end = command.find("\n", index)
            index = len(command) if end < 0 else end
            continue
        # Mask data boundaries before ordinary quotes/operators or statement splitting.
        if dialect == "bash" and not word and (command.startswith("((", index) or
                                                (command.startswith("[[", index) and command_position())):
            index = substitution_end(command, index, dialect, parsed, "[[" if char == "[" else char)
            continue
        if dialect == "powershell" and char == "@" and (end := here_string_end(command, index, parsed)) is not None:
            word.append("$OPAQUE")
            quoted = True
            index = end
            continue
        if dialect == "powershell" and command.startswith(("@(", "@{"), index):
            parsed.uncertain = True  # Array and hashtable arguments cannot establish certainty.
        if char == "{":
            if dialect == "bash":
                following = command[index + 1:index + 2]
                if not word and command_position() and (not following or following.isspace()):
                    parsed.uncertain = True  # A compound body may not execute.
                    result.append(Token("{", depth, start=index, end=index + 1))
                    index += 1
                    continue
                # Brace operands and parameter expansions obscure only this word;
                # the following outer operator still has a known meaning.
                end = (substitution_end(command, index, dialect, parsed, "{")
                       if word and word[-1].endswith("$") else index + 1)
                word.append("$OPAQUE")
                quoted = True
                index = end
                continue
            end = substitution_end(command, index, dialect, parsed, "{")
            parsed.uncertain |= bool(word)
            flush()
            # Reuse the same lexer for control bodies; their execution is always uncertain.
            first = None
            for token in reversed(result):
                if not token.quoted and token.value in SEPARATORS and token.depth <= depth:
                    break
                first = token
            if dialect == "powershell" and (grouping or (first and not first.quoted and
                                                         first.value.lower() in PS_COMPOUNDS)):
                parsed.uncertain = True
                body = tokens(command[index + 1:end - 1], dialect, grouping=True)
                parsed.uncertain |= body.uncertain
                result.append(Token("{", depth, start=index, end=index + 1))
                result.extend(Token(t.value, t.depth + depth, t.quoted, t.start + index + 1, t.end + index + 1)
                              for t in body.parts)
                result.append(Token("}", depth, start=end - 1, end=end))
            else:
                result.append(Token("$OPAQUE", depth, True, index, end))
            index = end
            continue
        if dialect == "bash" and char == "}" and (word or not command_position()):
            word.append("$OPAQUE")
            quoted = True
            index += 1
            continue
        if char in "'\"" or (char == "`" and dialect == "bash"):
            quote = char
            quoted = True
            if quote == "`":
                word.append("`")  # A substitution is never a literal mutation target.
            index += 1
            while index < len(command):
                char = command[index]
                if char == quote:
                    if dialect == "powershell" and command[index:index + 2] == quote * 2:
                        word.append(quote)
                        index += 2
                        continue
                    index += 1
                    break
                if quote != "'" and command.startswith("$(", index):
                    end = substitution_end(command, index, dialect, parsed)
                    word.append(command[index:end])
                    index = end
                    continue
                parsed.uncertain |= quote == '"' and char == "`" and dialect == "bash"
                if char == "\\" and dialect == "bash" and quote != "'" and index + 1 < len(command):
                    index += 1
                    char = command[index]
                elif char == "`" and dialect == "powershell" and quote == '"' and index + 1 < len(command):
                    index += 1
                    char = command[index]
                word.append(char)
                index += 1
            else:
                parsed.uncertain = True
            continue
        if command[index:index + 2] == "$(":
            # A command substitution is opaque to the outer call in both dialects.
            end = substitution_end(command, index, dialect, parsed)
            word.append(command[index:end])
            quoted = True
            index = end
            continue
        if char == "\\" and dialect == "bash" and index + 1 < len(command) and command[index + 1] in " &;|()<>\"'\\":
            word.append(command[index + 1])
            quoted = True
            index += 2
            continue
        if char == "`" and dialect == "powershell" and index + 1 < len(command):
            word.append(command[index + 1])
            quoted = True
            index += 2
            continue
        if char.isspace():
            flush()
            if char == "\n":
                result.append(Token(";", depth, start=index, end=index + 1))
            index += 1
            continue
        if dialect == "powershell" and char == ",":
            flush()
            parsed.uncertain = True  # Unquoted array arguments cannot establish certainty.
            index += 1
            continue
        if char in "&;|(){}<>":
            flush()
            operator = command[index:index + 3] if command[index:index + 3] in ("&>>", "<<<", "<<-") else command[index:index + 2]
            if operator not in ("&&", "||", "|&", "&>", "&>>", ">&", "<&", ">>", "<<", "<<<", "<<-", "<>"):
                operator = char
            if operator == ")":
                parsed.uncertain |= depth == 0
                depth = max(0, depth - 1)
            parsed.uncertain |= dialect == "bash" and operator == "(" and command_position()
            parsed.uncertain |= operator == "}"
            result.append(Token(operator, depth, start=index, end=index + len(operator)))
            if operator == "(":
                depth += 1
            index += len(operator)
            continue
        parsed.uncertain |= (char == "`" and dialect == "powershell") or (char == "\\" and dialect == "bash")
        word.append(char)
        index += 1
    flush()
    parsed.uncertain |= depth != 0
    return parsed


SEPARATORS = {";", "&&", "||", "|", "|&", "&", "{", "}"}
BASH_PREFIXES = {"if", "then", "elif", "else", "do", "while", "until", "!", "time"}
PS_COMPOUNDS = {"if", "elseif", "else", "foreach", "for", "while", "switch", "try", "catch", "finally", "foreach-object"}
LIST_VERBS = {"ls", "find", "tree", "du", "dir", "get-childitem", "gci"}
READ_VERBS = LIST_VERBS | {"cat", "head", "tail", "get-content", "gc", "type", "rg", "grep"}
PS_WRITE_VERBS = {"copy-item", "move-item", "remove-item", "set-content", "add-content", "out-file",
                  "new-item", "rename-item", "clear-content"}
WRITE_VERBS = {"cp", "mv", "rm", "tee"} | PS_WRITE_VERBS
CD_VERBS = {"cd", "pushd", "popd", "set-location", "sl", "push-location", "pop-location"}


REDIRECTIONS = {">", ">>", "&>", "&>>", ">&", "<", "<&", "<>", "<<", "<<-", "<<<"}


def redirections(group: list[Token], parsed: ShellParse | None = None) -> tuple[list[Token], list[str], list[str]]:
    """Remove redirect syntax before operand parsing; classify its own paths separately."""
    clean, writes, reads = [], [], []
    index = 0
    while index < len(group):
        part = group[index]
        if part.quoted or part.value not in REDIRECTIONS:
            clean.append(part)
            index += 1
            continue
        if (clean and not clean[-1].quoted and clean[-1].end == part.start
                and (clean[-1].value.isdecimal() or clean[-1].value == "*")):
            clean.pop()  # An adjacent descriptor prefix, not a command operand.
        if index + 1 < len(group):
            target = group[index + 1].value
            if part.value in (">", ">>", "&>", "&>>", "<>"):
                writes.append(target)
            elif part.value == ">&" and not re.fullmatch(r"(?:\d+-?|-)", target):
                # Bash >&word redirects both streams; >&2 duplicates a descriptor.
                writes.append(target)
            elif part.value == "<":
                reads.append(target)
        if parsed is not None:
            parsed.uncertain |= index + 1 == len(group) or (not group[index + 1].quoted and group[index + 1].value in REDIRECTIONS | {"(", ")"})
        index += 2
    return clean, writes, reads


def statements(parts: list[Token]) -> list[list[Token]]:
    groups, current = [], []
    for token in parts:
        if token.value in SEPARATORS and not token.quoted:
            if current:
                groups.append(current)
            current = []
        else:
            current.append(token)
    if current:
        groups.append(current)
    return groups


WRAPPER_OPTIONS = {
    "command": ({"-p"}, set()),
    "env": ({"-i", "--ignore-environment"}, {"-u", "--unset", "-C", "--chdir"}),
    "sudo": ({"-n", "--non-interactive", "-E", "-H"}, {"-u", "--user", "-g", "--group", "-C"}),
    "nice": (set(), {"-n", "--adjustment"}),
    "timeout": ({"--foreground", "--preserve-status", "-v", "--verbose"}, {"-s", "--signal", "-k", "--kill-after"}),
    "xargs": ({"-r", "--no-run-if-empty", "-t", "--verbose", "-0", "--null"},
              {"-n", "--max-args", "-P", "--max-procs", "-d", "--delimiter"}),
    "nohup": (set(), set()),
    "setsid": ({"-w", "--wait", "-f", "--fork", "-c", "--ctty"}, set()),
    "git": ({"--no-pager", "--paginate", "--bare", "--no-replace-objects"},
            {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}),
    "make": (set(), {"-C", "--directory", "-f", "--file", "--makefile"}),
    "start-process": ({"-wait", "-nonewwindow", "-passthru", "-loaduserprofile", "-usenewenvironment"},
                      {"-filepath", "-argumentlist", "-workingdirectory", "-credential", "-verb", "-windowstyle",
                       "-redirectstandardinput", "-redirectstandardoutput", "-redirectstandarderror"}),
}
DIRECTORY_OPTIONS = {"env": {"-C", "--chdir"}, "git": {"-C"}, "make": {"-C", "--directory"},
                     "start-process": {"-workingdirectory"}}


def verb(group: list[Token], os_family: str | None = None) -> tuple[str, list[Token], bool]:
    """Unwrap only known option forms; unsupported prefixes cannot establish certainty."""
    os_family = os_family or settings.detect_environment().split("/")[0]
    paths = ntpath if os_family == "windows" else posixpath
    useful = [t for t in group if t.value not in ("(", ")")]
    uncertain = False
    while useful:
        name = paths.basename(useful[0].value).lower().removesuffix(".exe")
        if not useful[0].quoted and useful[0].value in BASH_PREFIXES:
            uncertain = True
            useful = useful[1:]
            if name == "time" and useful and useful[0].value == "-p" and not useful[0].quoted:
                useful = useful[1:]
        elif re.match(r"^[A-Za-z_]\w*=", useful[0].value):
            useful = useful[1:]
        elif name in WRAPPER_OPTIONS:
            original = useful
            flags, operands = WRAPPER_OPTIONS[name]
            useful = useful[1:]
            while useful:
                option = useful[0].value.lower() if name == "start-process" else useful[0].value
                if not option.startswith("-"):
                    if name == "start-process":
                        useful = useful[1:]
                        continue
                    break
                if option == "--":
                    useful = useful[1:]
                    break
                uncertain |= option not in flags | operands or option in DIRECTORY_OPTIONS.get(name, set())
                if option in operands:
                    uncertain |= len(useful) < 2 or useful[1].value.startswith("-")
                    useful = useful[2:]
                else:
                    useful = useful[1:]
            if name in ("start-process", "git", "make"):
                return name, original[1:], uncertain
            if name == "timeout":
                uncertain |= not useful or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[smhd]?", useful[0].value)
                useful = useful[1:]
            uncertain |= not useful
        else:
            return name, useful[1:], uncertain
    return "", [], uncertain


def git_push(parts: list[Token], os_family: str | None = None) -> bool:
    for group in statements(parts):
        name, args, _ = verb(group, os_family)
        if name != "git":
            continue
        index = 0
        while index < len(args) and args[index].value.startswith("-"):
            option = args[index].value
            index += 2 if option in WRAPPER_OPTIONS["git"][1] else 1
        if index < len(args) and args[index].value == "push":
            return True
    return False


GIT_CHECKOUT_OPTIONS = ("-C", "--git-dir", "--work-tree")
GIT_CHECKOUT_VARIABLE = re.compile(r"(?:\$env:)?GIT_(?:DIR|WORK_TREE)(?:=|$)", re.I)


def _moves_checkout(token: Token) -> bool:
    """A wrapper's -C/--chdir (also attached, as getopt allows) or a GIT_DIR/GIT_WORK_TREE assignment."""
    value = token.value
    return (value in ("-C", "--chdir") or value.startswith(("--chdir=", "-C"))
            or bool(GIT_CHECKOUT_VARIABLE.match(value)))


def push_target_moved(parts: list[Token], os_family: str | None = None) -> bool:
    """True when a push picks its checkout inside the command: git -C/--git-dir/--work-tree,
    a wrapper's -C/--chdir, GIT_DIR/GIT_WORK_TREE, or an earlier directory change. The hook's
    cwd is then not the target."""
    moved = False
    for group in statements(parts):
        name, args, _ = verb(group, os_family)
        if name in CD_VERBS:
            moved = True
            continue
        if name != "git":
            # `export GIT_DIR=...;` or `$env:GIT_DIR = ...` before the push.
            moved |= any(GIT_CHECKOUT_VARIABLE.match(t.value) for t in group)
            continue
        useful = [t for t in group if t.value not in ("(", ")")]
        prefix = useful[:max(len(useful) - len(args) - 1, 0)]
        here = moved or any(_moves_checkout(t) for t in prefix)
        index = 0
        while index < len(args) and args[index].value.startswith("-"):
            option = args[index].value
            # Attached `-C<dir>` is refused by current Git, but stays advisory if a version accepts it.
            here |= option.split("=", 1)[0] in GIT_CHECKOUT_OPTIONS or (option.startswith("-C") and len(option) > 2)
            index += 2 if option in WRAPPER_OPTIONS["git"][1] else 1
        if here and index < len(args) and args[index].value == "push":
            return True
    return False


PYTHON_NO_OPERAND_FLAGS = {
    "-b", "-bb", "-B", "-d", "-E", "-i", "-I", "-O", "-OO", "-P", "-q", "-R", "-s", "-S", "-u", "-v", "-vv",
}


def external_direct(parts: list[Token], patterns: str, os_family: str) -> bool:
    paths = ntpath if os_family == "windows" else posixpath
    for group in statements(parts):
        values = [t.value for t in group if t.value not in ("(", ")")]
        if not values:
            continue
        name, arguments, _ = verb(group, os_family)
        # Recognize the executable, then its global options, rather than searching
        # data arguments for `ro.py external` or imposing a positional window.
        cli_args = [token.value for token in arguments]
        cli_name = name
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?|py", name):
            # Only flags that leave the following script operand intact qualify;
            # -c/-m and options with operands cannot establish this wrapper.
            while cli_args and (cli_args[0] in PYTHON_NO_OPERAND_FLAGS
                                or (name == "py" and re.fullmatch(r"-3(?:\.\d+)?", cli_args[0]))):
                cli_args = cli_args[1:]
            cli_name = paths.basename(cli_args[0]) if cli_args else ""
            cli_args = cli_args[1:]
        if cli_name in ("ro.py", "ro", "ro.cmd"):
            while cli_args:
                option, equal, _ = cli_args[0].partition("=")
                if option not in ("--project", "--slot", "--session"):
                    break
                if not equal and (len(cli_args) < 2 or cli_args[1].startswith("-")):
                    break
                cli_args = cli_args[1 if equal else 2:]
            if cli_args[:1] == ["external"]:
                continue
        text = " ".join(values)
        canonical = " ".join([name, *(token.value for token in arguments)])
        for pattern in patterns.split(";"):
            pattern = pattern.strip()
            if pattern in ("", "none"):
                continue
            if pattern.startswith("regex:"):
                if settings.safe_regex(pattern[6:]).search(text[:65536]):
                    return True
            else:
                prefix = pattern.removeprefix("literal:")
                if any(candidate == prefix or candidate.startswith(prefix + " ") for candidate in (text, canonical)):
                    return True
    return False


def mutation_paths(name: str, args: list[Token], root: Path | str, os_family: str) -> tuple[list[str], bool, bool]:
    """Resolve path operands, never data values. Unknown options cannot prove a mutation."""
    values = [t.value for t in args if t.value not in ("(", ")")]
    positional, explicit, destination = [], [], []
    uncertain, index, options, dry_run = False, 0, True, False
    recursive, target_directory, no_target_directory = False, False, False
    powershell = name in PS_WRITE_VERBS
    while index < len(values):
        value = values[index]
        option = value.lower() if powershell else value
        if value == "--":
            options = False
            index += 1
            continue
        if options and value.startswith("-"):
            if option in ("-path", "-literalpath", "-filepath"):
                if index + 1 < len(values):
                    explicit.append(values[index + 1])
                else:
                    uncertain = True
                index += 2
                continue
            if option in ("-destination", "-target-directory", "--target-directory", "-t"):
                if index + 1 < len(values):
                    destination.append(values[index + 1])
                else:
                    uncertain = True
                target_directory = option != "-destination"
                index += 2
                continue
            if option.startswith("--target-directory="):
                destination.append(value.split("=", 1)[1])
                target_directory = True
                index += 1
                continue
            if option in ("-value", "-inputobject", "-encoding", "-width", "-filter", "-include", "-exclude", "-itemtype", "-newname"):
                uncertain |= index + 1 == len(values)
                index += 2
                continue
            if value == "-T" or option == "--no-target-directory":
                no_target_directory = True
                index += 1
                continue
            if powershell and option == "-whatif":
                dry_run = True
            if option in ("-force", "-recurse", "-append", "-nonewline", "-noclobber", "-whatif", "-confirm",
                          "-passthru") or re.fullmatch(r"-[rRfapivnPTu]+", value) or option in (
                              "--recursive", "--force", "--append", "--no-clobber", "--verbose"):
                recursive = recursive or option in ("-recurse", "--recursive") or bool(re.fullmatch(r"-[rRfapivnPTu]+", value) and any(flag in value for flag in "rRa"))
                index += 1
                continue
            uncertain = True
            index += 1
            continue
        positional.append(value)
        index += 1
    if dry_run:
        return [], uncertain, False
    if name in ("cp", "copy-item", "mv", "move-item"):
        sources = explicit + (positional if destination else positional[:-1])
        targets = destination or positional[-1:]
        if not sources or not targets:
            return ["$UNRESOLVED_COPY_TARGET"], True, recursive
        effective = []
        paths = ntpath if os_family == "windows" else posixpath
        separators = "/\\" if os_family == "windows" else "/"
        for target in targets:
            resolved = normal_path(target, root, os_family)
            directory = (not no_target_directory and (target_directory or len(sources) > 1
                         or target.endswith(tuple(separators)) or target in (".", "..")
                         or (resolved is not None and Path(resolved).is_dir())))
            if directory:
                effective.extend(target.rstrip(separators) + "/" + paths.basename(source.rstrip(separators))
                                 for source in sources)
            else:
                effective.append(target)
        moving = name in ("mv", "move-item")
        return (sources if moving else []) + effective, uncertain, moving or recursive
    if name == "rename-item":
        # Renaming a directory changes every descendant's path, even without -Recurse.
        return explicit or positional[:1], uncertain, True
    if name in ("set-content", "add-content", "out-file", "new-item", "clear-content"):
        return explicit or positional[:1], uncertain, False
    return explicit + positional, uncertain, recursive


def command_parts(call: Call, values: dict[str, str]) -> ShellParse:
    """Parse known tool dialects; Environment still controls path semantics."""
    os_family = values.get("environment", settings.detect_environment()).split("/")[0]
    shell = call.dialect
    parsed = ShellParse()
    command = heredocs(call.command, parsed) if shell == "bash" else call.command
    if shell not in ("bash", "powershell"):
        words = re.findall(r'''"[^"\n]*"|'[^'\n]*'|[^\s;|&<>]+''', call.command.split("\n", 1)[0])
        return ShellParse([Token(word.strip("\"'"), 0, True) for word in words], uncertain=True)
    tokens(command, shell, parsed)
    parts = parsed.parts
    # Definitions cannot establish certainty; only outer tokens remain visible.
    if (any(verb(group, os_family)[0] in ("function", "alias", "set-alias", "new-alias") for group in statements(parts))
            or (shell == "bash" and any(not first.quoted and not second.quoted and (first.value, second.value) == ("(", ")")
                                        for first, second in zip(parts, parts[1:])))):
        parsed.uncertain = True
    for group in statements(parts):
        clean, _, _ = redirections(group, parsed)
        name, _, uncertain = verb(clean, os_family)
        parsed.uncertain |= uncertain or (shell == "bash" and bool(re.search(r"[$`]", name)))
    if shell == "powershell":
        for index, token in enumerate(parts):
            if token.value == "&" and not token.quoted and (index == 0 or parts[index - 1].value in SEPARATORS | {"("}):
                parsed.uncertain |= index + 1 == len(parts) or bool(re.search(r"[$`]", parts[index + 1].value.replace("$OPAQUE", "")))
    parsed.uncertain |= any(not t.quoted and t.value in ("[[", "]]", "--%") for t in parts)
    return parsed


def opaque(group: list[Token], os_family: str) -> bool:
    name, args, _ = verb(group, os_family)
    return (name in ("bash", "zsh", "sh", "powershell", "pwsh", "cmd") or
            (name.startswith("python") and any(t.value == "-c" for t in args)) or
            bool(re.search(r"[$`]", name)))


def foreground_wait(parsed: ShellParse, shell: str) -> int | None:
    """Find a final unconditional wait for every job in the current shell.

    A bare Bash wait, or PowerShell's complete job pipeline, keeps the call alive.
    Arguments, wrappers and uncertain/nested syntax cannot establish that boundary.
    """
    if parsed.uncertain:
        return None
    parts = parsed.parts
    end = len(parts)
    while end and not parts[end - 1].quoted and parts[end - 1].depth == 0 and parts[end - 1].value == ";":
        end -= 1
    expected = ("wait",) if shell == "bash" else ("get-job", "|", "wait-job")
    start = end - len(expected)
    if start < 0 or any(t.quoted or t.depth != 0 or
                        (t.value if shell == "bash" else t.value.lower()) != value
                        for t, value in zip(parts[start:end], expected)):
        return None
    if start:
        boundary = parts[start - 1]
        if boundary.quoted or boundary.depth != 0 or boundary.value not in (";", "&"):
            return None
        # A newline after &&, || or a pipe continues its conditional/pipeline;
        # it does not turn the wait into an unconditional final statement.
        previous = start - 1
        while previous >= 0 and not parts[previous].quoted and parts[previous].value == ";":
            previous -= 1
        if previous >= 0 and not parts[previous].quoted and parts[previous].value in ("&&", "||", "|", "|&"):
            return None
    return start


def shell_checks(call: Call, root: Path | str, jobs: list[dict], values: dict[str, str], parsed: ShellParse, *,
                 project_root: Path | str | None = None, cwd_uncertain: bool = False) -> list[Finding]:
    os_family = values.get("environment", settings.detect_environment()).split("/")[0]
    shell = call.dialect
    project_root = project_root if project_root is not None else root
    parts, bodies = parsed.parts, parsed.bodies
    found: list[Finding] = []
    if shell in ("bash", "powershell"):
        groups = statements(parts)
        changes = sum(verb(redirections(group)[0], os_family)[0] in CD_VERBS for group in groups)
        conditional_cwd = False
        previous_separator = ""
        waited_at = foreground_wait(parsed, shell)
        for index, part in enumerate(parts):
            if not part.quoted and part.value == "&" and not call.background:
                previous = parts[index - 1].value if index else ";"
                following = parts[index + 1].value if index + 1 < len(parts) else ";"
                background = shell == "bash" or (previous not in (";", "|", "{", "(", "&&", "||", "&")
                                                  and following in (";", "}"))
                waited = waited_at is not None and index < waited_at and part.depth == 0
                if background and not waited:
                    found.append(Finding("shell.background", "Use ro launch and a host background monitor for detached work."))
        for _, body, quoted in bodies:
            if not quoted and "`" in body:
                found.append(Finding("shell.heredoc", "Quote the heredoc delimiter before writing executable text."))
        for group_index, group in enumerate(groups):
            preceding = previous_separator
            if conditional_cwd and previous_separator != "&&":
                cwd_uncertain = True
            end = parts.index(group[-1]) + 1
            following = parts[end].value if end < len(parts) else ""
            previous_separator = following
            clean, redirects, reads = redirections(group)
            found.extend(path_checks(redirects, "jobs.mutate-bound", root, jobs, os_family, parsed=parsed,
                                     project_root=project_root, cwd_uncertain=cwd_uncertain))
            if opaque(clean, os_family):
                continue
            name, args, _ = verb(clean, os_family)
            if shell == "bash" and name == "disown" and not call.background:
                found.append(Finding("shell.background", "Use ro launch and a host background monitor for detached work."))
            if name == "start-job" or any(t.value in ("nohup", "setsid") for t in clean[:2]) or (name == "start-process" and not any(t.value.lower() == "-wait" for t in args)):
                found.append(Finding("shell.detach", "Use ro launch to retain process identity and a monitor."))
            top_level = next((t.depth == 0 for t in clean if t.value not in ("(", ")")), False)
            if (name in CD_VERBS and top_level and group_index == len(groups) - 1 and not call.background
                    and following in ("", ";") and preceding not in ("|", "|&", "&")):
                found.append(Finding("shell.cd", "Use the tool working-directory option for directory changes."))
            writes, uncertain, descendants = mutation_paths(name, args, root, os_family) if name in WRITE_VERBS else ([], False, False)
            parsed.uncertain |= uncertain
            found.extend(path_checks(writes, "jobs.mutate-bound", root, jobs, os_family, ancestor=descendants, parsed=parsed,
                                     project_root=project_root, cwd_uncertain=cwd_uncertain))
            if name in READ_VERBS:
                reads += [t.value for t in args if not t.value.startswith("-")] or ["."]
            if values.get("read_bound", "off") == "on":
                found.extend(path_checks(reads, "jobs.read-bound", root, jobs, os_family, parsed=parsed,
                                         project_root=project_root, cwd_uncertain=cwd_uncertain))
            if name in CD_VERBS:
                # Directory changes affect later relative operands, not parser certainty
                # or absolute operands. Redirects on this statement use the old cwd.
                operands = args[1:] if shell == "bash" and args and args[0].value == "--" else args
                directory = (normal_path(operands[0].value, root, os_family)
                             if len(operands) == 1 and not operands[0].value.startswith("-") else None)
                direct_cd = bool(clean) and (clean[0].value.lower() if shell == "powershell" else clean[0].value) == "cd"
                if (direct_cd and changes == 1 and top_level and following == "&&"
                        and preceding in ("", ";", "&&")
                        and directory is not None and not cwd_uncertain):
                    root = directory
                    conditional_cwd = True
                else:
                    cwd_uncertain = True
    direct = [t for group in statements(parts) if not opaque(group, os_family) for t in group + [Token(";", 0)]]
    if external_direct(direct, values.get("external_actions", "none"), os_family):
        found.append(Finding("external.gate", "Run this action through ro external with a current PASS receipt and prepared ledger entry."))
    return found


def certain_findings(parsed: ShellParse, findings: list[Finding]) -> list[Finding]:
    """One command-wide gate: uncertain parses warn, never block, including outer redirects."""
    if parsed.uncertain:
        findings = [Finding(f.check, f.message + " (uncertain parse)", True, f.identity) for f in findings]
    return list(dict.fromkeys(findings))


def path_checks(paths: list[str], check: str, root: Path | str, jobs: list[dict], os_family: str | None = None, *,
                ancestor: bool = False, parsed: ShellParse | None = None, project_root: Path | str | None = None,
                cwd_uncertain: bool = False) -> list[Finding]:
    os_family = os_family or settings.detect_environment().split("/")[0]
    project_root = project_root if project_root is not None else root
    root_path = normal_path(str(project_root), project_root, os_family)
    path_module = ntpath if os_family == "windows" else posixpath
    result = []
    from ro_jobs import protected_job

    for raw in paths:
        unknown_cwd = cwd_uncertain and not path_module.isabs(raw)
        path = None if unknown_cwd or (parsed is not None and parsed.uncertain) else normal_path(raw, root, os_family)
        for job in jobs:
            # Error/overrun/heartbeat outcomes may leave the owned process alive for inspection.
            if not protected_job(job):
                continue
            bound_paths = ([job.get("run_dir", ""), *job.get("bound", [])] if check == "jobs.mutate-bound"
                           else [job.get("run_dir", "")])
            job_identity = str(job.get("id") or job.get("run_dir") or "\0".join(job.get("bound", [])))
            identity = (job_identity, path if path is not None else raw)
            for bound in bound_paths:
                if not bound:
                    continue
                resolved = normal_path(bound, project_root, os_family)
                # A working directory is not a lock on every coordination file,
                # including for old job registries that bound the project root.
                if resolved and root_path and overlaps(root_path, resolved, os_family):
                    continue
                if path is None:
                    message = ("Working directory is uncertain; resolve it before checking this relative path."
                               if unknown_cwd else "Path may overlap a running job; resolve the literal path first.")
                    result.append(Finding(check, message, True, identity))
                elif resolved and overlaps(path, resolved, os_family, ancestor):
                    base = path.rsplit("/", 1)[-1]
                    if check == "jobs.read-bound" and (base == "status.json" or fnmatch.fnmatch(base, "*.log") or base.startswith("heartbeat")):
                        continue
                    result.append(Finding(check, "Path overlaps a running job; use its status, log or heartbeat file.",
                                          identity=identity))
    return list(dict.fromkeys(result))


def pre_checks(call: Call, root: Path, jobs: list[dict], values: dict[str, str], parsed: ShellParse | None = None,
               additional: list[Finding] | None = None, *, cwd: Path | str | None = None,
               cwd_uncertain: bool = False) -> list[Finding]:
    """Collect shell and publish evidence before applying command-wide certainty once."""
    os_family = values.get("environment", settings.detect_environment()).split("/")[0]
    directory = cwd if cwd is not None else root
    if call.tool == "shell":
        parsed = parsed if parsed is not None else command_parts(call, values)
        findings = shell_checks(call, directory, jobs, values, parsed, project_root=root,
                                cwd_uncertain=cwd_uncertain) + (additional or [])
        return certain_findings(parsed, findings)
    if call.tool in ("Edit", "Write", "NotebookEdit"):
        return path_checks(call.paths, "jobs.mutate-bound", directory, jobs, os_family,
                           project_root=root, cwd_uncertain=cwd_uncertain)
    if call.tool in ("Glob", "Grep", "Read") and values.get("read_bound", "off") == "on":
        return path_checks(call.paths or ["."], "jobs.read-bound", directory, jobs, os_family,
                           project_root=root, cwd_uncertain=cwd_uncertain)
    if call.tool == "AskUserQuestion" and values.get("autonomy") == "away":
        return [Finding("ask.away", "Ask in chat and continue only with work that needs no consent.")]
    if call.tool == "Agent":
        for requirement in values.get("brief_requirements", "none").split(";"):
            kind, sep, line = requirement.strip().partition(":")
            if sep and call.agent_type == kind.strip() and line.strip() not in call.prompt.splitlines():
                return [Finding("brief.requirements", "Agent brief is missing its configured required line.")]
    return []


def outcome(finding: Finding, values: dict[str, str], failure: bool = False) -> str:
    mode = values.get("enforcement", "off")
    if mode == "off":
        return "off"
    selected = {part.strip() for part in values.get("block", "none").split(",")}
    blocks = mode == "block" and finding.check in selected and not finding.uncertain
    if failure:
        blocks = False
    return "block" if blocks else "warn"
