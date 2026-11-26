from types import SimpleNamespace

from app.model.guards import check_meaning_preserved


def rec(original, suggestion):
    return SimpleNamespace(id="r1", type="L2.1.5", original=original, suggestion=suggestion)


def test_acronym_dropped_is_flagged_by_default():
    r = rec("Researchers at NASA found it.", "Researchers found it.")
    assert check_meaning_preserved([r])  # NASA lost


def test_acronym_kept_is_fine():
    r = rec("Researchers at NASA found it.", "Scientists at NASA found it.")
    assert check_meaning_preserved([r]) == []


def test_caps_emphasis_may_change_when_rule_on():
    r = rec("The crops were DAMAGED by drought.", "Drought damaged the crops.")
    assert check_meaning_preserved([r], skip_all_caps=True) == []


def test_caps_emphasis_flagged_when_rule_off():
    r = rec("The crops were DAMAGED by drought.", "Drought damaged the crops.")
    assert check_meaning_preserved([r])