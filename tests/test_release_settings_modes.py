"""Release checks follow compact settings and active-only reading pointers."""

from test_docs import release


def test_release_settings_gate_accepts_active_pointers_and_direct_edits():
    errors = []
    release.check_settings_modes(errors)
    assert errors == []


def test_initializer_validation_accepts_default_empty_pointer_set():
    errors = []
    release.check_initializer(errors)
    assert errors == []
