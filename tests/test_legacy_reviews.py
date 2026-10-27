"""5.1.0 evidence survives upgrade; the exception cannot approve new v3 reviews."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import sys

import pytest

from conftest import FIXTURES, NOW, SKILL, check, copy_fixture, found, init


FROZEN = {
    "agents.md": "3703dc983cf8b984941bf351b476b502fdf93cdcaa9a0f16c6303f4de253a6b5",
    "plan.md": "0008fc2d5d57f5ec962a28e6346fda9bce2b8d5f44e62a604da58914d359ce23",
    "discoveries.md": "82462d11e3bbdf628755de1ff45cc4a8d643b55a071725340852675bbbe37db3",
    "handoff.md": "e6f1f9aab20f108836111b763dd20dfd7abda768a00f4bfc236503560669d957",
}


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class FrozenClock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.replace(tzinfo=tz)
    monkeypatch.setattr(dt, "datetime", FrozenClock)


def reconfigure(target):
    return init.main([str(target), "--reconfigure"])


def frozen_project(tmp_path):
    return copy_fixture("v510-same-host", tmp_path / "project")


def test_frozen_510_discovery_passes_original_and_current_review_rules(tmp_path, monkeypatch):
    # Original checker at 713088d79745589b053ae02996670dc7147a8ee1, not a rewritten oracle.
    source = FIXTURES / "check_project_v510.py"
    assert hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "fdfd38cba391121bb9ee1f83427ad6dbd8b322214a0dfc5aeae98d2082421799")
    initializer = FIXTURES / "init_research_orchestrator_v510.py"
    assert hashlib.sha256(initializer.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "5bffd62c3fee90ebec30ea4ceed3ad2bf4707b37ea56311182375a4b2480b204")
    for name, digest in FROZEN.items():
        assert hashlib.sha256((FIXTURES / "v510-same-host" / name).read_bytes().replace(
            b"\r\n", b"\n")).hexdigest() == digest
    target = frozen_project(tmp_path)
    spec = importlib.util.spec_from_file_location("frozen_510_checker", source)
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    try:
        spec.loader.exec_module(legacy)
        init_spec = importlib.util.spec_from_file_location("frozen_510_init", initializer)
        old_init = importlib.util.module_from_spec(init_spec)
        init_spec.loader.exec_module(old_init)
        old_init.TEMPLATES = SKILL / "templates" / "v2"
        old = legacy.Checker(target)
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, "init_research_orchestrator", old_init)
            assert old.run() == 0, old.problems
        assert old.problems == []
    finally:
        sys.modules.pop(spec.name, None)
    current = check(target, NOW)
    assert not found(current, "ERROR") and not found(current, "WARN"), [i.render() for i in current.issues]
    assert current.discoveries["D-A-001"].fields["Cross-check"] == "VERIFIED"


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_upgrade_freezes_only_accepted_reviews_without_rewriting_evidence(tmp_path, workflow):
    target = frozen_project(tmp_path)
    discoveries = target / "discoveries.md"
    before = discoveries.read_bytes()
    args = [str(target), "--reconfigure", "--workflow", workflow, "--user", "operator"]
    if workflow == "unified":
        args.append("--migrate")
    assert init.main(args) == 0
    assert discoveries.read_bytes() == before
    agents = (target / "agents.md").read_text(encoding="utf-8")
    assert agents.count("<!-- ro-legacy-reviews: v2 ") == 1
    current = check(target, NOW)
    assert not found(current, check_id="discovery.review.ineligible")
    assert not found(current, check_id="discovery.state.unbacked")
    # Portability does not depend on ignored machine-local metadata.
    (target / ".ro" / "template-render.json").unlink()
    assert not found(check(target, NOW), check_id="discovery.state.unbacked")
    assert reconfigure(target) == 0
    assert (target / "agents.md").read_text(encoding="utf-8").count("ro-legacy-reviews:") == 1


@pytest.mark.parametrize("upgrade", [False, True])
def test_new_timestamped_same_host_review_follows_v3_even_in_legacy_project(tmp_path, upgrade):
    target = frozen_project(tmp_path)
    if upgrade:
        assert reconfigure(target) == 0
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    new = text[text.index("## D-A-001"):].replace("D-A-001", "D-A-002").replace(
        "same host —", "same host — reviewed 2026-10-20T10:00 —")
    path.write_text(text + "\n" + new, encoding="utf-8", newline="\n")
    current = check(target, NOW)
    assert [i.record for i in found(current, check_id="discovery.review.ineligible")] == ["D-A-002"]
    assert [i.record for i in found(current, check_id="discovery.state.unbacked")] == ["D-A-002"]


@pytest.mark.parametrize("change", ["new-id", "review", "evidence", "source", "timestamp", "session"])
def test_preservation_is_bound_to_original_record_and_review(tmp_path, change):
    target = frozen_project(tmp_path)
    assert reconfigure(target) == 0
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "new-id": ("D-A-001", "D-A-002"),
        "review": ("independently compared", "new reviewer compared"),
        "evidence": ("comparison.txt", "other-comparison.txt"),
        "source": ("- Source: A", "- Source: B"),
        "timestamp": ("same host —", "same host — reviewed 2026-10-20T10:00 —"),
        "session": ("- Cross-check:", "- Session: claude-code:A@2026-10-05T08:00\n- Cross-check:"),
    }
    path.write_text(text.replace(*replacements[change]), encoding="utf-8", newline="\n")
    assert found(check(target, NOW), check_id="discovery.state.unbacked")


@pytest.mark.parametrize("marker", ["<!-- ro-legacy-reviews: v2 * -->", "<!-- ro-legacy-reviews: v3 " + "a" * 64 + " -->"])
def test_malformed_preservation_metadata_fails_closed(tmp_path, marker):
    target = frozen_project(tmp_path)
    assert reconfigure(target) == 0
    path = target / "agents.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(marker if "ro-legacy-reviews:" in line else line for line in lines) + "\n",
                    encoding="utf-8", newline="\n")
    current = check(target, NOW)
    assert found(current, "ERROR", "discovery.legacy.invalid")
    assert found(current, "ERROR", "discovery.state.unbacked")


def test_a_new_legacy_shaped_review_after_upgrade_is_not_preserved(tmp_path):
    target = frozen_project(tmp_path)
    assert reconfigure(target) == 0
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\n" + text[text.index("## D-A-001"):].replace("D-A-001", "D-A-002"),
                    encoding="utf-8", newline="\n")
    assert reconfigure(target) == 0
    current = check(target, NOW)
    assert [i.record for i in found(current, "ERROR", "discovery.state.unbacked")] == ["D-A-002"]


@pytest.mark.parametrize("new_field", ["timestamp", "session"])
def test_even_matching_fingerprints_cannot_bless_v3_review_records(tmp_path, new_field):
    target = frozen_project(tmp_path)
    assert reconfigure(target) == 0
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    if new_field == "timestamp":
        text = text.replace("same host —", "same host — reviewed 2026-10-20T10:00 —")
    else:
        text = text.replace("- Cross-check:", "- Session: claude-code:A@2026-10-05T08:00\n- Cross-check:")
    path.write_text(text, encoding="utf-8", newline="\n")
    current = check(target, NOW)
    disc = current.discoveries["D-A-001"]
    digest = current.review_fingerprint(disc, current.parse_reviews(disc, "discoveries.md")[0])
    agents = target / "agents.md"
    lines = agents.read_text(encoding="utf-8").splitlines()
    agents.write_text("\n".join(f"<!-- ro-legacy-reviews: v2 {digest} -->" if "ro-legacy-reviews:" in line
                                else line for line in lines) + "\n", encoding="utf-8", newline="\n")
    assert found(check(target, NOW), "ERROR", "discovery.state.unbacked")


def test_preserved_acceptance_does_not_clear_a_later_challenge(tmp_path):
    target = frozen_project(tmp_path)
    assert reconfigure(target) == 0
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    original_review = text.splitlines()[-1]
    text += "  - Codex (B): CHALLENGED — reviewed 2026-10-20T10:00 — checksum inputs differ\n"
    text += original_review + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    assert found(check(target, NOW), "ERROR", "discovery.state.challenged")
