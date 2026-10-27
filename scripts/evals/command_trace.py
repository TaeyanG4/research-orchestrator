"""Read bounded CLI execution evidence; never evaluate recorded shell code."""
from __future__ import annotations

from dataclasses import dataclass
import re
import shlex


@dataclass(frozen=True)
class RoCommand:
    subcommand: str
    job: str | None
    position: tuple[int, int]


def _source(command: str) -> str:
    """Codex serializes a shell wrapper using POSIX argument quoting on every OS."""
    try:
        words = shlex.split(command)
    except ValueError:
        return command
    if words and (words[0].replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
                  in {"powershell", "pwsh", "bash", "sh", "zsh"}):
        for index, word in enumerate(words[:-1]):
            if word.lower() in {"-command", "-c", "-lc"}:
                return words[index + 1]
    return command


def _statements(source: str):
    lexer = shlex.shlex(source, posix=True, punctuation_chars=";|&()\n=")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.escape = ""  # Preserve Windows path separators.
    statement = []
    try:
        for token in lexer:
            # shlex groups adjacent punctuation, including a newline followed
            # by PowerShell's call operator; keep that operator on the next call.
            words = re.split(r"([;|\n]+|&&)", token) if all(char in ";|&()\n=" for char in token) else [token]
            for word in filter(None, words):
                if all(char in ";|\n" for char in word) or word == "&&":
                    if statement:
                        yield statement
                    statement = []
                else:
                    statement.append(word)
    except ValueError:
        return  # An incomplete quoted command does not establish an invocation.
    if statement:
        yield statement


def ro_commands(executions: list[dict]) -> list[RoCommand]:
    """Resolve simple aliases and job variables with per-invocation CLI output.

    Unknown shell expressions are not interpreted. A variable job argument can
    instead be identified by a unique monitor outcome in that same successful
    tool call; a literal conflicting ID never inherits another job's outcome.
    """
    result = []
    variable = re.compile(r"\$(?:[A-Za-z_]\w*|\{[A-Za-z_]\w*\})\Z")
    job_id = re.compile(r"J-[A-Z]+-\d+\Z")
    for index, execution in enumerate(executions):
        values = {}
        source = _source(execution.get("command", ""))
        powershell = bool(re.search(r"(?m)^\s*\$\w+\s*=", source))
        output = execution.get("aggregated_output", "")
        launched = re.findall(r"(?m)^(J-[A-Z]+-\d+) launched; confirmed alive(?:;[^\r\n]*)?\r?$", output)
        monitored = re.findall(r"(?m)^- Job: (J-[A-Z]+-\d+); item [^;]+; outcome: .+", output)
        launch_index = monitor_index = 0

        def variable_name(value):
            name = value.strip("${}")
            return name.lower() if powershell else name

        def resolve(value):
            return values.get(variable_name(value), value) if variable.fullmatch(value) else value

        for offset, statement in enumerate(_statements(source)):
            words = statement
            if len(words) >= 3 and words[1] == "=" and re.fullmatch(r"\$?\w+", words[0]):
                name = variable_name(words[0])
                words = words[2:]
                values.pop(name, None)
                if len(words) == 1:
                    value = resolve(words[0])
                    if not value.startswith("$") or variable.fullmatch(value):
                        values[name] = value
                    continue
                if words[0].lower() == "join-path" and len(words) == 3:
                    values[name] = resolve(words[-1])
                    continue
            if words and words[0] == "&":
                words = words[1:]
            words = [resolve(word) for word in words]
            if not words:
                continue
            executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
            if re.fullmatch(r"(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?", executable):
                words = words[1:]
                while words:
                    if words[0].startswith("-X") and words[0] != "-X":
                        words = words[3:] if len(words) > 2 and words[1] == "=" else words[1:]
                    elif re.fullmatch(r"-u|-B|-E|-S|-3(?:\.\d+)?", words[0]):
                        words = words[1:]
                    elif words[0] == "-X" and len(words) > 1:
                        words = words[4:] if len(words) > 3 and words[2] == "=" else words[2:]
                    else:
                        break
            if not words or words[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in {"ro", "ro.py"}:
                continue
            words = words[1:]
            while words and words[0].split("=", 1)[0] in {"--slot", "--session", "--project"}:
                words = words[2:] if len(words) > 1 and words[1] != "=" else words[3:]
            if not words or words[0] not in {"launch", "monitor", "close"} or "--help" in words or "-h" in words:
                continue
            subcommand, job = words[0], None
            if subcommand == "launch":
                if launch_index < len(launched):
                    job = launched[launch_index]
                launch_index += 1
            elif subcommand == "monitor":
                argument = words[1] if len(words) == 2 else ""
                if job_id.fullmatch(argument):
                    job = argument
                elif variable.fullmatch(argument) and monitor_index < len(monitored):
                    job = monitored[monitor_index]
                monitor_index += 1
            result.append(RoCommand(subcommand, job, (index, offset)))
    return result
