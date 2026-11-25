from app.model import guards
from app.model.level3_future import adapted_ui_spec as spec

LIMITS = ("MAX_ITEMS", "MAX_CHANGES", "MAX_ITEM_CHARS", "MAX_LABEL_CHARS")


def test_limits_are_defined_once():
    for name in LIMITS:
        assert getattr(spec, name) == getattr(guards, name), name


def test_limits_actually_enforced_by_spec():
    # the spec's validation uses the shared label limit
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        spec.SetLinkText(block_id="a-1", text="x" * (guards.MAX_LABEL_CHARS + 1), expected_original="old")