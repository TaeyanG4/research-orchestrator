"""Checker command line: exit codes, --strict, output with check ids (spec §7)."""

from __future__ import annotations

from conftest import item, make_project, run_check_cli, set_queue, set_slot, unified_project


def test_exit_codes_and_strict(tmp_path) -> None:
    clean = make_project(tmp_path, "clean", "--preset", "team-research")
    ok = run_check_cli(clean)
    assert ok.returncode == 0 and ok.stdout.startswith("CONSISTENCY: OK")

    warned = unified_project(tmp_path)
    set_queue(warned, item("H-A-01", "B since 2026-10-24 09:00"))
    set_slot(warned, "B", "released", "none")
    normal = run_check_cli(warned)
    assert normal.returncode == 0 and "WARN plan.claim.stale" in normal.stdout
    strict = run_check_cli(warned, "--strict")
    assert strict.returncode == 1

    set_queue(warned, item("H-A-01", claimed=None))
    failing = run_check_cli(warned)
    assert failing.returncode == 1 and "ERROR plan.claim.missing" in failing.stdout

    (clean / "plan.md").unlink()
    missing = run_check_cli(clean)
    assert missing.returncode == 2 and "missing plan.md" in missing.stdout
