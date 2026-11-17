
from bs4 import BeautifulSoup

from app.model.level3_future.adapted_renderer import apply_adapted_spec
from app.model.level3_future.adapted_ui_spec import AdaptedUISpec


def render(html, *changes):
    return apply_adapted_spec(html, AdaptedUISpec.model_validate({"changes": list(changes)}))


def test_resolves_all_document_order_ids_before_structural_changes():
    result = render(
        "<p>Plan for 2026 in Toronto.</p><ul><li>Original item</li></ul>",
        {"block_id": "p-1", "action": "text_to_list", "list_type": "bulleted",
         "items": ["Plan for 2026.", "Meet in Toronto."], "expected_original": "Plan for 2026 in Toronto."},
        {"block_id": "li-1", "action": "set_style", "value": "font-weight: 700"},
    )
    soup = BeautifulSoup(result.html, "html.parser")
    assert result.skipped == {}
    assert soup.find_all("li")[-1].get_text() == "Original item"
    assert soup.find_all("li")[-1]["style"] == "font-weight: 700"


def test_list_conversion_skips_rich_inline_content_without_losing_it():
    html = '<p>Read the <a href="/guide">Toronto guide</a> in 2026.</p>'
    result = render(
        html,
        {"block_id": "p-1", "action": "text_to_list", "list_type": "bulleted",
         "items": ["Read the Toronto guide.", "Use it in 2026."],
         "expected_original": "Read the Toronto guide in 2026."},
    )
    assert 0 in result.skipped and "inline formatting" in result.skipped[0]
    assert 'href="/guide"' in result.html


def test_accessibility_actions_preserve_attributes_and_names():
    html = """<a href="/guide" class="cta">click here</a>
    <button><svg></svg></button><button>Submit</button>
    <img src="garden.jpg" alt="image"><section><p>Students plant beans.</p></section>"""
    result = render(
        html,
        {"block_id": "a-1", "action": "set_link_text", "text": "Read the garden guide", "expected_original": "click here"},
        {"block_id": "button-1", "action": "add_button_label", "label": "Open menu", "placement": "after_icon"},
        {"block_id": "button-2", "action": "set_button_label", "label": "Submit application", "expected_original": "Submit"},
        {"block_id": "img-1", "action": "set_alt_text", "alt": "Students planting a garden", "expected_original": "image"},
        {"block_id": "section-1", "action": "add_section_heading", "heading": "Garden activities", "expected_original": "Students plant beans."},
    )
    soup = BeautifulSoup(result.html, "html.parser")
    assert result.skipped == {}
    assert soup.a["href"] == "/guide" and soup.a["class"] == ["cta"] and soup.a.get_text() == "Read the garden guide"
    assert soup.find_all("button")[0]["aria-label"] == "Open menu"
    assert soup.find_all("button")[1]["aria-label"] == "Submit application"
    assert soup.img["alt"] == "Students planting a garden"
    assert soup.section.find("h2").get_text() == "Garden activities"


def test_menu_grouping_preserves_item_order():
    result = render(
        "<ul><li>One</li><li>Two</li><li>Three</li></ul>",
        {"block_id": "ul-1", "action": "group_menu_items", "groups": [
            {"label": "First", "item_ids": ["li-1", "li-2"]},
            {"label": "Second", "item_ids": ["li-3"]},
        ]},
    )
    soup = BeautifulSoup(result.html, "html.parser")
    assert [li.get_text() for li in soup.ul.find_all("li", recursive=False)] == ["First", "One", "Two", "Second", "Three"]


# ---- visible text: no stray spaces, buttons and images read from their attributes ----

import pytest  # noqa: E402

from app.model.level3_future.adapted_renderer import block_text, visible_text  # noqa: E402


def tag_of(html, name="p"):
    return BeautifulSoup(html, "html.parser").find(name)


@pytest.mark.parametrize("html,expected", [
    ('<p>See <a href="/x">the guide</a>, then <b>try it</b>.</p>', "See the guide, then try it."),   # no space before , or .
    ("<p>Costs (<em>see below</em>) apply.</p>", "Costs (see below) apply."),
    ("<ul><li>one</li><li>two</li></ul>", "one two"),                                                    # blocks are separated
    ("<p>first<br>second</p>", "first second"),
    ("<p>  lots \n of   space </p>", "lots of space"),
    ("<p>shown<script>hidden()</script><!-- note --><style>p{}</style></p>", "shown"),
])
def test_visible_text(html, expected):
    assert visible_text(tag_of(html, "p" if html.startswith("<p") else "ul")) == expected


def test_block_text_reads_alt_and_value_and_falls_back_to_visible_text():
    assert block_text(tag_of('<img src="a.png" alt="A coin jar">', "img")) == "A coin jar"
    assert block_text(tag_of('<img src="a.png">', "img")) == ""
    assert block_text(tag_of('<input type="submit" value="OK">', "input")) == "OK"
    assert block_text(tag_of("<button>Go <b>now</b></button>", "button")) == "Go now"


# ---- replace_text keeps links and bold ----

LINKED = '<p>Students compare ways to save money. See <a href="/guide">the guide</a>, then <b>try it</b>.</p>'
LINKED_TEXT = "Students compare ways to save money. See the guide, then try it."


def test_replace_text_keeps_links_and_bold_around_the_edit():
    result = render(LINKED, {"block_id": "p-1", "action": "replace_text",
                             "value": "Students look at ways to save money. See the guide, then try it."})
    assert result.skipped == {}
    assert '<a href="/guide">the guide</a>' in result.html and "<b>try it</b>" in result.html
    assert visible_text(BeautifulSoup(result.html, "html.parser").p) == "Students look at ways to save money. See the guide, then try it."


def test_replace_text_on_a_plain_block_still_replaces_it():
    result = render("<p>Old words here.</p>", {"block_id": "p-1", "action": "replace_text", "value": "New words here."})
    assert result.html == "<p>New words here.</p>" and result.skipped == {}


def test_a_word_inside_a_link_can_be_edited_in_place():
    result = render(LINKED, {"block_id": "p-1", "action": "replace_text", "value": LINKED_TEXT.replace("the guide", "the handbook")})
    assert '<a href="/guide">the handbook</a>' in result.html and result.skipped == {}


def test_an_edit_that_spans_a_link_boundary_is_skipped_and_the_markup_is_kept():
    result = render(LINKED, {"block_id": "p-1", "action": "replace_text", "value": LINKED_TEXT.replace("money. See the guide", "cash. Read the manual")})
    assert 0 in result.skipped and "markup is kept" in result.skipped[0]
    assert result.html == LINKED   # untouched


def test_an_edit_in_the_middle_of_a_word_does_not_cut_it_in_half():
    result = render('<p>Save <a href="/x">money</a> and saved time.</p>',
                    {"block_id": "p-1", "action": "replace_text", "value": "Save money and saving time."})
    assert result.skipped == {}
    assert visible_text(BeautifulSoup(result.html, "html.parser").p) == "Save money and saving time."
    assert '<a href="/x">money</a>' in result.html


def test_an_ambiguous_edit_is_skipped_rather_than_applied_in_the_wrong_place():
    html = '<p>Go <a href="/x">now</a>. Go now. Go now.</p>'
    result = render(html, {"block_id": "p-1", "action": "replace_text", "value": "Go now. Go now. Go later."})
    if result.skipped:
        assert result.html == html
    else:   # if it was applied, it must be exactly what was asked for
        assert visible_text(BeautifulSoup(result.html, "html.parser").p) == "Go now. Go now. Go later."


def test_set_link_text_preserves_icon_and_updates_existing_accessible_name():
    html = '<a href="/guide" aria-label="click here"><svg><path d="x"></path></svg><span>click here</span></a>'
    result = render(
        html,
        {
            "block_id": "a-1",
            "action": "set_link_text",
            "text": "Read the guide",
            "expected_original": "click here",
        },
    )
    soup = BeautifulSoup(result.html, "html.parser")
    assert result.skipped == {}
    assert soup.a.svg is not None and soup.a.span.get_text() == "Read the guide"
    assert soup.a["href"] == "/guide" and soup.a["aria-label"] == "Read the guide"
