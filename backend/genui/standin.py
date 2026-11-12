"""A rule-based stand-in for the model, used ONLY when MODEL_MOCK=1.

It reads the same prompt data a real model gets and answers in the same JSON shape, so tests, CI and a demo without a
model go through the real pipeline (guardrails, re-measure gate, preview, apply). It is deliberately simple and is not
the product: with a real model (Ollama, Claude, anything OpenAI-format) none of this code runs.
"""
import json
import re

_SPLIT_AT = re.compile(r",\s+(?:and|but|so|which|because)\s+|\s+(?:and|but|because|although|while)\s+|;\s+|,\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_VAGUE_BUTTONS = {"submit": "Submit form", "ok": "Confirm choice", "go": "Go to next page"}


def _page_data(messages: list[dict]) -> dict:
    user = next(m["content"] for m in messages if m["role"] == "user")
    return json.loads(re.search(r"<page_data>\n(.*)\n</page_data>", user, re.S).group(1))


def _split_sentence(sentence: str) -> str | None:
    """Cut one long sentence into two at the connecting word nearest the middle."""
    ending = sentence[-1] if sentence[-1] in ".!?" else "."
    body = sentence.rstrip(".!?")
    options = sorted(_SPLIT_AT.finditer(body), key=lambda m: abs(m.start() - len(body) / 2))
    for m in options:
        first, second = body[: m.start()].rstrip(",; "), body[m.end():].strip()
        if len(first.split()) >= 4 and len(second.split()) >= 4:
            return f"{first}. {second[0].upper()}{second[1:]}{ending}"
    return None


def _halves(text: str) -> list[str] | None:
    sentences = _SENTENCE_END.split(text)
    if len(sentences) < 2:
        return None
    mid = len(sentences) // 2
    return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]


def _slug_words(href: str) -> str:
    stem = re.sub(r"\.\w+$", "", href.rstrip("/").rsplit("/", 1)[-1])
    return " ".join(w for w in re.split(r"[-_ ]+", stem) if w and not w.isdigit()) or "this page"


def _proposal(finding: dict, data: dict) -> dict | None:
    m, bid, measured = finding["metric_id"], finding["block_id"], finding["measured"]
    block = next((b for b in data["blocks"] if b["block_id"] == bid), {})
    base = {"metric_id": m, "block_id": bid, "severity": "medium"}

    def make(change: dict, why: str) -> dict:
        return {**base, "rationale": why, "change": change}

    if m in {"T3", "T4"} and measured.get("sentence"):
        value = _split_sentence(measured["sentence"])
        if value:
            return make({"action": "replace_text", "original": measured["sentence"], "value": value}, "Long sentence cut in two.")
    if m == "S1" and block.get("text"):
        parts = _halves(block["text"])
        if parts:
            return make({"action": "split_paragraph", "parts": parts}, "Paragraph cut into shorter ones.")
    if m == "J5":
        return make({"action": "set_link_text", "text": f"Read about {_slug_words(block.get('href', ''))}"[:40]}, "Link text now says where it goes.")
    if m == "J11":
        hint = (block.get("hint") or "").split()
        return make({"action": "add_button_label", "label": (" ".join(hint[:2]).title() if hint else "Open")[:40], "placement": "after_icon"},
                    "Icon-only button gets a visible label.")
    if m == "J12":
        return make({"action": "set_alt_text", "alt": f"Picture showing {_slug_words(block.get('file_name', ''))}"}, "Alt text describes the image.")
    if m == "J14":
        label = _VAGUE_BUTTONS.get(measured.get("label", ""), "Continue to next step")
        return make({"action": "set_button_label", "label": label}, "Button label now has a verb and an object.")
    if m == "S3":
        words = " ".join((block.get("text") or "Section").split()[:4])
        return make({"action": "add_section_heading", "heading": words.rstrip(".,;:"), "level": 2}, "Section gets a heading.")
    if m == "S2":
        anchors = [a for a in data.get("anchors", []) if a in {b["block_id"] for b in data["blocks"]}]
        pick = anchors[len(anchors) // 2] if anchors else None
        if pick:
            text = next(b["text"] for b in data["blocks"] if b["block_id"] == pick)
            heading = " ".join(text.split()[:4]).rstrip(".,;:")
            return {**base, "block_id": pick, "rationale": "Long page gets a heading.",
                    "change": {"action": "add_heading_before", "heading": heading, "level": 2}}
    if m == "M1":
        return make({"action": "stop_autoplay"}, "Media no longer starts by itself.")
    if m == "L3":
        return make({"action": "set_style", "value": "font-size: 18px"}, "Text size raised.")
    if m == "L2":
        css = "line-height: 1.6" + ("; text-align: left" if measured.get("text_align") == "justify" else "")
        return make({"action": "set_style", "value": css}, "Line spacing opened up.")
    if m == "L1":
        return make({"action": "set_style", "value": "max-width: 70ch"}, "Line length limited.")
    if m in {"S5", "N8"} and block.get("items"):
        size = 6 if m == "N8" else 7
        items = block["items"]
        groups = [items[i : i + size] for i in range(0, len(items), size)]
        if len(groups) >= 2:
            return make({"action": "split_list", "groups": [
                {"label": f"Group {n + 1}", "item_ids": [i["block_id"] for i in g]} for n, g in enumerate(groups)]},
                "Long list grouped.")
    return None


def standin_caller(messages: list[dict], *, task: str, config=None, transport=None) -> str:
    data = _page_data(messages)
    proposals = [p for f in data["findings"] if (p := _proposal(f, data))]
    return json.dumps({"proposals": proposals})
