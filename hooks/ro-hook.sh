#!/bin/sh
# Preserve an existing root separator: //agents.md is a UNC lookup on Windows.
ro_hook_join() {
    case "$1" in
        */) ro_hook_path=$1$2 ;;
        *) ro_hook_path=$1/$2 ;;
    esac
}

# Unrelated projects need no interpreter and leave host input untouched.
ro_hook_cwd=$PWD
ro_hook_project=
for ro_hook_start in "$ro_hook_cwd" "${CLAUDE_PROJECT_DIR:-}" "${CODEX_PROJECT_DIR:-}"; do
    [ -n "$ro_hook_start" ] || continue
    CDPATH= cd -P "$ro_hook_cwd" 2>/dev/null || break
    CDPATH= cd -P "$ro_hook_start" 2>/dev/null || continue
    ro_hook_dir=$PWD
    while :; do
        ro_hook_join "$ro_hook_dir" agents.md
        if [ -f "$ro_hook_path" ]; then
            ro_hook_project=$ro_hook_dir
            break
        fi
        # Physical PWD can retain a drive letter in Windows shells. UNC shares
        # are roots too: their server is not a project ancestor.
        case "$ro_hook_dir" in
            /|[A-Za-z]:|[A-Za-z]:/) break ;;
            //*)
                ro_hook_unc=${ro_hook_dir#//}
                case "$ro_hook_unc" in */*/*) ;; *) break ;; esac
                ;;
        esac
        ro_hook_parent=${ro_hook_dir%/*}
        # A separator-free path has no parent; every continuing step shrinks.
        [ "$ro_hook_parent" != "$ro_hook_dir" ] || break
        ro_hook_dir=${ro_hook_parent:-/}
    done
    [ -n "$ro_hook_project" ] && break
done
CDPATH= cd -P "$ro_hook_cwd" 2>/dev/null || exit 0
if [ -z "$ro_hook_project" ]; then
    printf '{}\n'
    exit 0
fi
# Question/delegation subscriptions stay installed as policy changes. Read only
# the governing setting here so inactive tools need no interpreter or host input.
ro_hook_policy_quiet() {
    command -v grep >/dev/null 2>&1 || return 1
    ro_hook_join "$ro_hook_project" agents.md
    ro_hook_lines=$(LC_ALL=C grep -i "$1" "$ro_hook_path")
    ro_hook_status=$?
    [ "$ro_hook_status" -ne 1 ] || return 0
    [ "$ro_hook_status" -eq 0 ] || return 1
    printf '%s\n' "$ro_hook_lines" | LC_ALL=C grep -i -v "^[[:space:]]*-[[:space:]]*$1:[[:space:]]*$2[[:space:]]*$" >/dev/null
    [ "$?" -eq 1 ]
}
if [ "$1" = PreToolUse ] && [ "$2" = --tool ]; then
    case "$3" in
        ask) if ro_hook_policy_quiet 'Autonomy' 'present'; then printf '{}\n'; exit 0; fi ;;
        agent) if ro_hook_policy_quiet 'Brief requirements' 'none'; then printf '{}\n'; exit 0; fi ;;
    esac
fi
# Timestamp witnesses are written only after Python acknowledges record changes
# and pending warnings. This shortcut reads state files, never host stdin.
ro_hook_post_clean() {
    [ "${RO_HOOK_DIAGNOSTICS:-}" != 1 ] || return 1
    ro_hook_join "$ro_hook_project" .ro
    ro_hook_state=$ro_hook_path
    [ ! -e "$ro_hook_state/hook-diagnostics.on" ] || return 1
    [ -f "$ro_hook_state/records-hook.ready" ] || return 1
    IFS= read -r ro_hook_ready < "$ro_hook_state/records-hook.ready" || return 1
    [ "$ro_hook_ready" = records-hook-v1 ] || return 1
    for ro_hook_name in agents.md plan.md discoveries.md handoff.md records-hook.json warnings.log warnings-shown.json; do
        case "$ro_hook_name" in
            *.md) ro_hook_join "$ro_hook_project" "$ro_hook_name" ;;
            *) ro_hook_join "$ro_hook_state" "$ro_hook_name" ;;
        esac
        ro_hook_source=$ro_hook_path
        ro_hook_stamp=$ro_hook_state/records-hook-stamps/$ro_hook_name
        if [ -f "$ro_hook_source" ]; then
            [ -f "$ro_hook_stamp" ] || return 1
            [ ! "$ro_hook_source" -nt "$ro_hook_stamp" ] && [ ! "$ro_hook_stamp" -nt "$ro_hook_source" ] || return 1
            IFS= read -r ro_hook_expected < "$ro_hook_stamp" || return 1
            case "$ro_hook_expected" in ''|*[!0-9]*) return 1 ;; esac
            if command -v wc >/dev/null 2>&1; then
                ro_hook_size=$(LC_ALL=C wc -c < "$ro_hook_source") || return 1
            else
                # Minimal shells may lack utilities. Keep the fallback independent
                # of Python and stop counting as soon as the known size is exceeded.
                ro_hook_size=$(
                    LC_ALL=C
                    export LC_ALL
                    ro_hook_bytes=0
                    ro_hook_line=
                    while IFS= read -r ro_hook_line; do
                        ro_hook_bytes=$((ro_hook_bytes + ${#ro_hook_line} + 1))
                        [ "$ro_hook_bytes" -le "$ro_hook_expected" ] || exit 1
                    done < "$ro_hook_source"
                    printf '%s' "$((ro_hook_bytes + ${#ro_hook_line}))"
                ) || return 1
            fi
            [ "$ro_hook_expected" -eq "$ro_hook_size" ] 2>/dev/null || return 1
        elif [ -e "$ro_hook_source" ] || [ -e "$ro_hook_stamp" ]; then
            return 1
        fi
    done
    [ -f "$ro_hook_state/records-hook.json" ]
}
if [ "$1" = PostToolUse ] && ro_hook_post_clean; then
    printf '{}\n'
    exit 0
fi
# Stop and edit checks only protect registered jobs. Recovery state also counts:
# losing the primary registry must not make outstanding jobs disappear.
if [ "$1" = Stop ] || { [ "$1" = PreToolUse ] && [ "$2" = --tool ] && [ "$3" = edit ]; }; then
    ro_hook_join "$ro_hook_project" .ro/jobs.json
    ro_hook_jobs=$ro_hook_path
    ro_hook_join "$ro_hook_project" .ro/recovery/jobs.json
    if [ ! -e "$ro_hook_jobs" ] && [ ! -e "$ro_hook_path" ]; then
        printf '{}\n'
        exit 0
    fi
fi
# Select an installed interpreter without starting a separate version probe.
# Installed skill layout (install.py): <skill>/hooks next to <skill>/scripts; plugin layout otherwise.
case "$0" in
    */*) ro_hook_file=$0 ;;
    *) ro_hook_file=$(command -v "$0" 2>/dev/null) || ro_hook_file=$0
       case "$ro_hook_file" in */*) ;; *) ro_hook_file=./$ro_hook_file ;; esac ;;
esac
runner="${ro_hook_file%/*}/../scripts/ro_hook_runner.py"
[ -f "$runner" ] || runner="${ro_hook_file%/*}/../skills/research-orchestrator/scripts/ro_hook_runner.py"
# Use the same explicitly selected interpreter for supervisor and child.
if [ -n "${RO_HOOK_PYTHON:-}" ]; then
    if [ -x "$RO_HOOK_PYTHON" ]; then
        exec "$RO_HOOK_PYTHON" -E -S "$runner" "$@" --policy-root "$ro_hook_project"
    fi
    printf '%s\n' 'hooks inactive: configured Python interpreter unavailable' >&2
    printf '{}\n'
    exit 0
fi
for interpreter in python3 python; do
    path=$(command -v "$interpreter" 2>/dev/null) || continue
    case "$path" in
        # Windows Store placeholders print a message and exit; they are not interpreters.
        */WindowsApps/*) continue ;;
    esac
    RO_HOOK_PYTHON="$path"
    # Native Windows Python compares Win32 paths, not Git Bash's /c/... spelling.
    if command -v cygpath >/dev/null 2>&1; then
        RO_HOOK_PYTHON=$(cygpath -w "$path")
    fi
    export RO_HOOK_PYTHON
    exec "$path" -E -S "$runner" "$@" --policy-root "$ro_hook_project"
done
# Git Bash on Windows can also use the Python launcher.
if command -v py >/dev/null 2>&1; then
    # The launcher is not the interpreter; resolve once on this fallback path.
    path=$(py -3 -E -S -c 'import sys; print(sys.executable)' 2>/dev/null)
    if [ -x "$path" ]; then
        RO_HOOK_PYTHON="$path"
        export RO_HOOK_PYTHON
        exec "$path" -E -S "$runner" "$@" --policy-root "$ro_hook_project"
    fi
fi
printf '%s\n' 'hooks inactive: missing Python 3 interpreter' >&2
printf '{}\n'
exit 0
