"""Per-session runtime and configuration isolation, without handling credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
import tomllib


EXCLUDED = {"evals", "tests", "fixtures", "__pycache__", ".git", ".codex", ".agents"}
MODEL_KEYS = {"model", "model_provider", "model_reasoning_effort", "model_reasoning_summary",
              "model_verbosity", "service_tier", "model_context_window", "model_auto_compact_token_limit"}
PROVIDER_KEYS = {"name", "base_url", "wire_api", "env_key", "requires_openai_auth",
                 "request_max_retries", "stream_max_retries", "stream_idle_timeout_ms"}
# Codex config.schema.json and `codex features list`; no unsupported `features.skills` switch.
OVERRIDES = [
    "approval_policy=\"never\"", "sandbox_workspace_write.writable_roots=[]",
    "sandbox_workspace_write.exclude_tmpdir_env_var=true",
    "sandbox_workspace_write.exclude_slash_tmp=true", "sandbox_workspace_write.network_access=false",
    "project_root_markers=[]", "skills.include_instructions=false", "skills.bundled.enabled=false",
    "features.skip_host_skill_discovery=true",
    "features.skill_search=false", "features.plugins=false", "features.apps=false",
    "features.hooks=false", "features.memories=false", "features.multi_agent=false",
    "shell_environment_policy.experimental_use_profile=false", "web_search=\"disabled\"",
]


def plain_tree(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise ValueError(f"Links are not supported in eval trees: {path}")
    for entry in path.rglob("*"):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError(f"Links are not supported in eval trees: {entry}")


def stage_runtime(source: Path, target: Path) -> None:
    plain_tree(source)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*EXCLUDED, "*.pyc", "*.pyo"))
    for path in [*target.rglob("*"), target]:
        path.chmod(path.stat().st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def configured_model_settings() -> dict:
    """Retain model selection and the host sandbox backend, never instructions or credentials."""
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    path = home / "config.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    profile = config.get("profiles", {}).get(config.get("profile"), {})
    selected = {**config, **profile}
    settings = {key: selected[key] for key in MODEL_KEYS if key in selected}
    provider = selected.get("model_provider")
    provider_config = selected.get("model_providers", {}).get(provider)
    if provider_config:
        settings["model_providers"] = {provider: {key: value for key, value in provider_config.items()
                                                if key in PROVIDER_KEYS}}
    # --ignore-user-config also drops the Windows execution backend. With no backend
    # selected, workspace-write + approval_policy=never rejects shell execution. Keep
    # only this enum (not host permissions, writable roots, rules, or shell commands).
    windows = selected.get("windows", {})
    if isinstance(windows, dict) and windows.get("sandbox") in {"elevated", "unelevated", "mxc"}:
        settings["windows"] = {"sandbox": windows["sandbox"]}
    return settings


def host_instruction_context() -> dict:
    """Snapshot host instruction paths and AGENTS.md size, never file contents."""
    home = Path.home().resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex")).resolve()
    agents = codex_home / "AGENTS.md"
    try:
        size = agents.stat().st_size
    except FileNotFoundError:
        size = None
    roots = [home / name / "skills" for name in (".codex", ".agents", ".claude")]
    roots.append(codex_home / "skills")
    return {
        "user_home": str(home), "codex_home": str(codex_home),
        "home_variables": {key: str(Path(value).resolve()) for key in ("HOME", "USERPROFILE")
                           if (value := os.environ.get(key))},
        "installed_skill_roots": list(dict.fromkeys(str(path) for path in roots)),
        "global_agents": {"path": str(agents), "exists": size is not None,
                          "size_bytes": size, "empty": size == 0 if size is not None else None},
    }


def prepare_environment(root: Path, project: Path, settings: dict) -> tuple[dict, dict]:
    """Keep host homes so Windows reuses its sandbox setup; suppress discovery with options."""
    host_context = host_instruction_context()
    temp = project / ".eval-tmp"
    temp.mkdir()
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8",
                   "PYTHONDONTWRITEBYTECODE": "1", "TMP": str(temp), "TEMP": str(temp), "TMPDIR": str(temp),
                   "RESEARCH_ORCHESTRATOR_HOME": str(project / ".eval-ro-home")}
    # Do not inherit Python startup/search paths or app-owned session/config routing; keep the
    # variable the retained provider authenticates with (its `env_key`).
    keep = {"CODEX_HOME", "CODEX_API_KEY"} | {fields["env_key"] for fields in settings.get("model_providers", {}).values()
                                              if isinstance(fields.get("env_key"), str)}
    for key in list(environment):
        if ((key.startswith("CODEX_") and key not in keep)
                or key in {"PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME"}):
            environment.pop(key)
    metadata = {
        "runtime_excluded_names": sorted(EXCLUDED | {"*.pyc", "*.pyo"}),
        "writable_roots": [str(project)], "runtime_read_only": True,
        "interpreter_access": "default workspace-write full-disk read; no additional writable grant",
        "fresh_codex_home": False, "fresh_user_home": False, "credential_files_accessed": False,
        "host_context": host_context,
        "model_settings_retained": sorted(settings), "config_overrides": OVERRIDES,
        "windows_sandbox": settings.get("windows", {}).get("sandbox"),
        "residual_risks": [
            "Default sandbox read access can expose source/eval files if deliberately searched; this is not a read jail.",
            "Codex home state is shared with the host, including existing Windows sandbox setup.",
            "Installed skills are disabled by options and audited for visible access, not removed.",
            "Global AGENTS.md is checked by size only; visible access to a non-empty file is audited.",
            "System-managed Codex configuration and inherited environment authentication remain host dependencies.",
        ],
    }
    return environment, metadata


def config_arguments(settings: dict) -> list[str]:
    """TOML scalar encoding is JSON-compatible for the allowlisted values."""
    overrides = list(OVERRIDES)
    for key, value in settings.items():
        if key == "model_providers":
            for provider, fields in value.items():
                for name, setting in fields.items():
                    # Codex's -c parser splits dotted keys literally, so a quoted segment is not unquoted.
                    key = provider if re.fullmatch(r"[A-Za-z0-9_-]+", provider) else json.dumps(provider)
                    overrides.append(f"model_providers.{key}.{name}={json.dumps(setting)}")
        elif key == "windows":
            overrides.append(f"windows.sandbox={json.dumps(value['sandbox'])}")
        else:
            overrides.append(f"{key}={json.dumps(value)}")
    return ["--ignore-user-config", "--ignore-rules", "--ephemeral",
            *[part for value in overrides for part in ("-c", value)]]


def cleanup(root: Path) -> list[str]:
    """Clear Windows read-only bits and retry transient locks; diagnostics never fail a run."""
    problems = []

    def retry_read_only(function, path, error):
        entry = Path(path)
        if entry.parent.is_relative_to(root) and not entry.parent.is_symlink() and not entry.parent.is_junction():
            entry.parent.chmod(entry.parent.stat().st_mode | stat.S_IWUSR | stat.S_IREAD)
        if not entry.is_symlink() and not entry.is_junction():
            entry.chmod(entry.stat().st_mode | stat.S_IWUSR | stat.S_IREAD)
        function(path)

    for attempt in range(3):
        try:
            # rmtree does not recurse through junctions/symlinks; do not chmod their targets.
            if root.exists():
                shutil.rmtree(root, onexc=retry_read_only)
            return problems
        except OSError as exc:
            problems.append(f"Cleanup attempt {attempt + 1}: {exc}")
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
    problems.append(f"Temporary directory remains: {root}")
    return problems
