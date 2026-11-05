from bs4 import BeautifulSoup

from app.model.adapted_renderer import apply_adapted_spec
from app.model.adapted_ui_spec import AdaptedUISpec


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
