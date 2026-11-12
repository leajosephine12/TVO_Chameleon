"""The four actions added for general accessibility: split_paragraph, explain_term, add_heading_before, stop_autoplay."""
import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.model.adapted_renderer import apply_adapted_spec
from app.model.adapted_ui_spec import AdaptedUISpec


def render(html, *changes):
    return apply_adapted_spec(html, AdaptedUISpec.model_validate({"changes": list(changes)}))


TEXT = "Plants need light. They also need water and soil. Roots hold the plant in place."


def test_split_paragraph_cuts_without_rewriting_and_keeps_attributes():
    result = render(
        f'<p class="lead">{TEXT}</p>',
        {"block_id": "p-1", "action": "split_paragraph",
         "parts": ["Plants need light.", "They also need water and soil.", "Roots hold the plant in place."],
         "expected_original": TEXT},
    )
    paragraphs = BeautifulSoup(result.html, "html.parser").find_all("p")
    assert result.skipped == {}
    assert [p.get_text() for p in paragraphs] == ["Plants need light.", "They also need water and soil.", "Roots hold the plant in place."]
    assert all(p["class"] == ["lead"] for p in paragraphs)


def test_split_paragraph_spec_rejects_rewritten_words():
    with pytest.raises(ValidationError, match="exactly the words"):
        AdaptedUISpec.model_validate({"changes": [
            {"block_id": "p-1", "action": "split_paragraph", "parts": ["Plants need light.", "They need water."],
             "expected_original": TEXT}]})


def test_split_paragraph_skips_stale_text_and_rich_content():
    stale = render("<p>Something else entirely.</p>", {"block_id": "p-1", "action": "split_paragraph",
                                                       "parts": ["Plants need light.", "They also need water and soil. Roots hold the plant in place."],
                                                       "expected_original": TEXT})
    assert "no longer matches" in stale.skipped[0]
    rich = render(f"<p><b>Plants need light.</b> They also need water and soil. Roots hold the plant in place.</p>",
                  {"block_id": "p-1", "action": "split_paragraph",
                   "parts": ["Plants need light.", "They also need water and soil. Roots hold the plant in place."],
                   "expected_original": TEXT})
    assert "inline formatting" in rich.skipped[0]
    assert "<b>Plants need light.</b>" in rich.html


def test_explain_term_wraps_the_first_whole_word_and_keeps_the_text():
    html = "<p>NASA flew. Later NASA flew again, and UNASA did not.</p>"
    result = render(html, {"block_id": "p-1", "action": "explain_term", "term": "NASA",
                           "explanation": "National Aeronautics and Space Administration",
                           "expected_original": "NASA flew. Later NASA flew again, and UNASA did not."})
    soup = BeautifulSoup(result.html, "html.parser")
    abbrs = soup.find_all("abbr")
    assert result.skipped == {} and len(abbrs) == 1
    assert abbrs[0]["title"] == "National Aeronautics and Space Administration" and abbrs[0].get_text() == "NASA"
    assert soup.p.get_text() == "NASA flew. Later NASA flew again, and UNASA did not."


def test_explain_term_skips_a_term_that_is_missing_or_already_explained():
    missing = render("<p>Plain words only.</p>", {"block_id": "p-1", "action": "explain_term", "term": "NASA",
                                                   "explanation": "Space agency", "expected_original": "Plain words only."})
    assert "was not found" in missing.skipped[0]
    done = render('<p><abbr title="Space agency">NASA</abbr> flew.</p>',
                  {"block_id": "p-1", "action": "explain_term", "term": "NASA", "explanation": "Space agency",
                   "expected_original": "NASA flew."})
    assert "already explained" in done.skipped[0]


def test_add_heading_before_inserts_a_heading_in_front_of_the_block():
    result = render("<p>First.</p><p>Second part of the page.</p>",
                    {"block_id": "p-2", "action": "add_heading_before", "heading": "Second part", "level": 3,
                     "expected_original": "Second part of the page."})
    soup = BeautifulSoup(result.html, "html.parser")
    assert result.skipped == {}
    assert [t.name for t in soup.find_all(True)] == ["p", "h3", "p"]
    assert soup.h3.get_text() == "Second part"


def test_add_heading_before_refuses_the_wrong_places():
    html = "<h2>Title</h2><p>Body text.</p><ul><li>Item</li></ul>"
    in_front_of_li = render(html, {"block_id": "li-1", "action": "add_heading_before", "heading": "Items",
                                   "expected_original": "Item"})
    assert "cannot be placed" in in_front_of_li.skipped[0]
    twice = render(html, {"block_id": "p-1", "action": "add_heading_before", "heading": "Body",
                          "expected_original": "Body text."})
    assert "already in front" in twice.skipped[0]


def test_stop_autoplay_removes_autoplay_and_shows_controls():
    result = render('<video autoplay src="a.mp4"></video><audio src="b.mp3"></audio>',
                    {"block_id": "video-1", "action": "stop_autoplay"},
                    {"block_id": "audio-1", "action": "stop_autoplay"})
    soup = BeautifulSoup(result.html, "html.parser")
    assert not soup.video.has_attr("autoplay") and soup.video.has_attr("controls")
    assert result.skipped == {1: "the media does not autoplay"}


def test_target_size_css_is_allowed():
    result = render('<a href="/x">Go to the guide</a>',
                    {"block_id": "a-1", "action": "set_style", "value": "min-height: 44px; min-width: 44px"})
    assert result.skipped == {} and "min-height: 44px" in result.html


def test_split_list_makes_several_lists_under_headings_and_keeps_every_item():
    html = '<ul class="menu" id="m"><li>One</li><li>Two</li><li>Three</li><li>Four</li></ul>'
    result = render(html, {"block_id": "ul-1", "action": "split_list", "level": 3, "groups": [
        {"label": "First half", "item_ids": ["li-1", "li-2"]}, {"label": "Second half", "item_ids": ["li-3", "li-4"]}]})
    soup = BeautifulSoup(result.html, "html.parser")
    assert result.skipped == {}
    assert [t.name for t in soup.find_all(["h3", "ul"])] == ["h3", "ul", "h3", "ul"]
    lists = soup.find_all("ul")
    assert [[li.get_text() for li in ul.find_all("li")] for ul in lists] == [["One", "Two"], ["Three", "Four"]]
    assert all(ul.get("class") == ["menu"] and not ul.has_attr("id") for ul in lists)


def test_split_list_skips_when_the_groups_do_not_cover_the_list_in_order():
    result = render("<ul><li>One</li><li>Two</li><li>Three</li></ul>", {"block_id": "ul-1", "action": "split_list", "groups": [
        {"label": "A", "item_ids": ["li-2"]}, {"label": "B", "item_ids": ["li-1", "li-3"]}]})
    assert "do not match" in result.skipped[0]
    assert BeautifulSoup(result.html, "html.parser").find_all("ul").__len__() == 1
