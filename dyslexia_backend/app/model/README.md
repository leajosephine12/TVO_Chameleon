# Model layer

The "model side" of the app: three functions that ask an AI model for recommendations, check what comes back, and either
return valid data or a clear error. It works with a **mock** (no model needed) today and a **real model** (Ollama on this
computer, or RunPod later) by changing settings only. No code changes.

```
Backend  --calls-->  generate_text_recommendations / generate_layout_recommendations / generate_adapted_ui
                         |
                         +--> call_model()  --mock-->  fixed, valid JSON
                                            --real-->  POST {MODEL_BASE_URL}/chat/completions   (Ollama, RunPod, any OpenAI-style server)
```

Everything lives in `dyslexia_backend/app/model/`. It imports the team's `Recommendation` from `app/schemas.py` and does not
change any teammate file. **Importing it does not need `fastmcp`** (a test checks this).

## What each file does

| File | Purpose |
|---|---|
| `config.py` | Reads settings from environment variables (and an optional `.env`) |
| `client.py` | `call_model()`: the mock or the real HTTP call, chosen by settings |
| `mock.py` | The mock's fixed replies |
| `runner.py` | The shared loop: ask, parse, validate, retry with the error fed back, else a clear error. Logs timing |
| `guards.py` | The safety checks (numbers, quoting, facts kept) and the quoting of page text as data |
| `prompts.py` | Rules shared by every prompt |
| `text_recs.py` | Call 1: `generate_text_recommendations(blocks, findings)` |
| `layout_recs.py` | Call 2: `generate_layout_recommendations(screenshot, metrics)` (needs a vision model) |
| `adapted_ui.py`, `adapted_ui_model.py`, `adapted_ui_spec.py` | Call 3: `generate_adapted_ui(...)`, plain code by default, model version optional, placeholder spec |
| `standin_analyze_text.py` | A **stand-in** for the team's `analyze_text`, plain code |
| `sample_data.py` | The two real TVO paragraphs and clearly-fake findings, used by tests and demos |
| `log.py` | `enable_timing_logs()` |

Outside this folder I added only: `dyslexia_backend/tests/`, `pytest.ini`, `requirements-model.txt`, `scripts/`, `samples/`, `.env.example`.

---

## Setup on Windows PowerShell (from scratch)

You need Python 3.10 or newer (this was built on 3.13). Check with `python --version`.

**1. Open PowerShell and go to the backend folder.** Adjust the path to where you cloned the repo:

```powershell
cd C:\Users\<you>\Desktop\Projects_UofT\TVO_Chameleon\dyslexia_backend
```

**2. Make a virtual environment** (a private folder of Python packages for this project, so nothing else on your computer is affected):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell says "running scripts is disabled", run this once for the current window only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Your prompt should now start with `(.venv)`. You must activate again in every new PowerShell window.

**3. Install the packages:**

```powershell
pip install -r requirements-model.txt
```

**4. Run the tests** (they need no model and no internet):

```powershell
python -m pytest
```

You should see all tests pass.

### Mock mode (no model needed)

The mock returns fixed, valid replies so the UI and backend can be built and demoed.

```powershell
$env:MODEL_MOCK = "1"
python scripts/smoke_test.py --full --vision
```

`$env:NAME = "value"` sets a setting for the current PowerShell window only. It is forgotten when you close the window.
To use the mock from your own Python code, set `MODEL_MOCK=1` in the environment that runs the backend.

### Real mode with Ollama

1. Install Ollama from <https://ollama.com/download> and start it (it runs in the background; the default address is `http://localhost:11434`).
2. Download a model. The tag below exists on ollama.com (6.1 GB, takes text and images) but **was not checked on this computer**:

   ```powershell
   ollama pull gemma4:e4b-it-qat
   ollama list
   ```

   Use the exact name that `ollama list` shows for `MODEL_NAME`.
3. Switch the mock off and point at Ollama:

   ```powershell
   Remove-Item Env:MODEL_MOCK -ErrorAction SilentlyContinue
   $env:MODEL_BASE_URL = "http://localhost:11434/v1"
   $env:MODEL_NAME = "gemma4:e4b-it-qat"
   $env:MODEL_REASONING_EFFORT = "none"
   python scripts/smoke_test.py
   ```

   The smoke test prints the mode, the server, the models the server has (and warns if yours is not among them), the model's reply, and **how many seconds it took**.
4. Then try the real calls, which also show per-attempt timing and retries:

   ```powershell
   python scripts/smoke_test.py --full      # call 1 on the two TVO paragraphs
   python scripts/smoke_test.py --vision    # call 2 with a tiny test image (the model must accept images)
   ```

> **`MODEL_REASONING_EFFORT=none` matters.** Gemma 4 is a "thinking" model. Without it, the first real call took 9+ minutes on this laptop and was rejected.

**Reading the timing lines.** Each attempt prints one line, for example
`task=text_recs attempt=2/3 retry=True model_call=41.20s outcome=ok total=83.10s`.
`retry=True` means the first reply was invalid and the model was asked again, and the `rejected because:` lines under it say why. If each `model_call` takes minutes, the model is too
slow for this computer: try a smaller model, or set `MODEL_MAX_RETRIES=0` to stop after one attempt.

### What it costs on a laptop (measured)

Measured on the development laptop: Intel Iris Xe graphics (no usable GPU, so Ollama runs on the **CPU**), 13.7 GB RAM, Windows 11, Ollama 0.40.13,
`MODEL_REASONING_EFFORT=none`, the two TVO paragraphs, one run each. Times will differ on other machines.

| Call | `gemma4:e4b-it-qat` (6.1 GB) | `gemma4:e2b-it-qat` (4.3 GB) |
|---|---|---|
| Tiny request, model already loaded | 4 to 8 s | 3 to 4 s |
| Tiny request, model not loaded yet | about 40 to 50 s | about 26 s |
| Call 1, text (2 paragraphs) | 198 s, 0 retries, 7 recommendations | 102 s, 0 retries, 5 recommendations |
| Call 2, layout (1x1 test image, fake metrics) | 198 s, 0 retries, 6 recommendations | 75 s, 0 retries, 3 recommendations |

- Output length is what costs time (about 4 tokens per second on this CPU), not the prompt. Fewer or shorter recommendations means a faster call.
- Ollama unloads an idle model after about 5 minutes, so the next call pays the loading time again.
- e4b writes better rationales (it quotes the numbers, e.g. "24 words") and splits long sentences into two; e2b is twice as fast but its rationales are generic ("This sentence is too long") and it skipped some difficult words.
- A real demo against these models needs minutes per page. For live demos use the mock or the saved `samples/`.

### Using a `.env` file instead of typing settings

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env.example` has `MODEL_MOCK=1` switched on, so change it (or remove that line) when you want the real model.
`scripts/smoke_test.py` reads `.env` by itself. In your own code call `load_env_file(".env")` from `app.model.config`.
A value typed in PowerShell beats the file. `.env` is in `.gitignore`; never commit it or paste keys into code.

### Settings

| Setting | Meaning | Default |
|---|---|---|
| `MODEL_MOCK` | `1` = use the mock | off |
| `MODEL_BASE_URL` | OpenAI-style server address | `http://localhost:11434/v1` (Ollama) |
| `MODEL_NAME` | Model to ask for (required in real mode) | none |
| `MODEL_API_KEY` | Optional key, sent as `Authorization: Bearer ...`. Environment only | none |
| `MODEL_TIMEOUT` | Seconds to wait for one reply | `120` |
| `MODEL_REASONING_EFFORT` | `none`, `low`, `medium` or `high`, sent as `reasoning_effort`. **Use `none` with Gemma 4 on Ollama** (it is a "thinking" model; otherwise each call can take 9+ minutes on a CPU laptop) | not sent |
| `MODEL_MAX_RETRIES` | Extra attempts after an invalid reply (`2` means up to 3 calls) | `2` |

Later, for RunPod: set `MODEL_BASE_URL` to its OpenAI-compatible URL, `MODEL_NAME` to the served model, and `MODEL_API_KEY` to your key (in the environment, never in code).

### Troubleshooting

| You see | Meaning |
|---|---|
| `MODEL_NAME is not set` | Real mode but no model chosen. Set `MODEL_NAME`, or `MODEL_MOCK=1` |
| `Could not reach the model at ...` | Ollama is not running, or the address is wrong |
| `Model server returned HTTP 404` | Usually the model name is wrong (not pulled). Compare with `ollama list` |
| `still invalid after 3 attempts` | The model answered but never in a valid form. The reasons are printed. A bigger model or a better prompt may help |
| Image call fails | The model may not support images; check its tags on ollama.com |

---

## Using it from code

```python
from app.model.text_recs import generate_text_recommendations
from app.model.layout_recs import generate_layout_recommendations
from app.model.adapted_ui import generate_adapted_ui
from app.model.standin_analyze_text import standin_analyze_text

recs  = generate_text_recommendations(blocks, standin_analyze_text(blocks))   # list[Recommendation], all "pending"
lrecs = generate_layout_recommendations(screenshot_png_bytes, metrics)        # list[Recommendation]
result = generate_adapted_ui(accepted_text, accepted_layout, blocks)          # result.spec, result.skipped
```

Calls 1 and 2 return a **plain `list[Recommendation]`**, ready for `/analyze` (the model's `{"recommendations": [...]}` wrapper is removed inside this layer).
They raise `ModelConfigError` (bad settings), `ModelCallError` (server unreachable or bad HTTP reply) or `ModelOutputError`
(the model never produced valid output after the retries). They never return invalid data.

**What every call enforces:** a prompt plus a JSON schema; validation of the reply; up to `MODEL_MAX_RETRIES` retries that feed
the exact problems back to the model; every number in a rationale must appear in the provided findings (the model copies numbers, it never
calculates them); `original` must be quoted exactly from the page; digits and names in the original must survive in the suggestion;
page text is passed as JSON-quoted data inside `<page_data>` tags and the prompt states it is never an instruction.

## Findings contract (PROPOSAL for the owner of `analyze_text`)

> **This shape is a proposal, not an agreed contract.** No `analyze_text` exists on the branch yet, so the model layer was written against the shape below.
> If your tool returns something different, tell the model-layer owner or change `sample_data.py` and the prompt in `text_recs.py`.

`generate_text_recommendations(blocks, findings)` takes:

- `blocks`: the page text, `[{"block_id": "p-1", "text": "..."}]`. Ids are `<tag>-<n>` in document order, the same ids `analyze_html` uses.
- `findings`: the tool's measurements. The model copies numbers from here and never calculates them. Every number in a rationale is checked against this object.

Example input (the numbers are fake):

```json
{
  "blocks": [{"block_id": "p-1", "text": "Students compare different ways ... or taking advantage of sales. ..."}],
  "findings": {
    "targets": {"grade_level": "3-5", "max_sentence_words": "15-20"},
    "blocks": [{
      "block_id": "p-1",
      "word_count": 66,
      "reading_grade": 12.4,
      "long_sentences": [{"text": "Students compare different ways ... advantage of sales.", "word_count": 24}],
      "difficult_words": ["consumers", "compound", "technology"]
    }]
  }
}
```

Example output (a plain list, the team's shared recommendation format, all `pending`):

```json
[{
  "id": "r1", "block_id": "p-1", "type": "long_sentence",
  "original": "Students compare different ways ... advantage of sales.",
  "suggestion": "Students compare different ways ... money. Examples are using reward programs or taking advantage of sales.",
  "rationale": "24 words; Grade 3-5 target <= 15-20",
  "evidence": "readability tool / W3C COGA",
  "severity": "medium", "status": "pending"
}]
```

What the tool must provide: any number a rationale may quote (word counts, grade levels, targets) as a plain number or inside a string. Extra fields are fine.

## Layout metrics contract (PROPOSAL for the owner of `layout_metrics`)

> Also a proposal. No `layout_metrics` tool exists on the branch yet.

`generate_layout_recommendations(screenshot, metrics)` takes a screenshot (PNG/JPEG/WebP bytes, or base64 text) and:

```json
{"blocks": [{"block_id": "p-1", "font_size_px": 14, "line_height": 1.2, "line_length_chars": 96}]}
```

The reference targets are added by the model layer from `app/guidelines.py` (imported, not copied), so the tool does not send targets.
The output is a plain list of recommendations in the shared format. This call needs a vision-capable model.

## Stand-in for `analyze_text`

`standin_analyze_text.py` is a **stand-in** (plain code, no model) that produces findings in the proposed shape, so call 1 can run end to end today:

```python
findings = standin_analyze_text(blocks)
recs = generate_text_recommendations(blocks, findings)
```

It is flagged `"STAND_IN": true` in its output. Replace it with the team's real `analyze_text` when that exists. Its readability grade is Flesch-Kincaid and its syllable, sentence and difficult-word detection are rough heuristics.

## Call 3: `generate_adapted_ui` (placeholder GenUI spec)

> **The spec is a placeholder** (`adapted_ui_spec.py`): `{"changes": [{"block_id", "action": "replace_text|set_style", "value"}]}`. Swap the real schema in that file and in the two builders.

```python
result = generate_adapted_ui(text_recs, layout_recs, blocks)                 # plain code (recommended, default)
result = generate_adapted_ui(text_recs, layout_recs, blocks, use_model=True) # model version
result.spec      # the placeholder spec
result.skipped   # accepted recommendations that could not become a change, each with a reason
```

- Only `accepted` / `edited` recommendations are used; pending and denied are ignored. For `edited`, `suggestion` holds the user's own text.
- `blocks` is needed because `replace_text` carries the whole new block text (one block can have several accepted edits). Question for the GenUI owner: would a phrase-level change (original + replacement) suit the renderer better?
- `set_style` values are checked against a safe list of CSS properties; `replace_text` must be plain text. The renderer must insert it as text, never as HTML.
- Structural suggestions such as "break into steps" are reported in `skipped`, because the placeholder spec cannot express them.

**Recommendation: use the plain-code version.** Once the user has accepted a change, turning it into a spec is deterministic. Code gives the same answer every time, cannot reword what the user approved, needs no model call (no wait on a laptop, no cost), and is easy to test. The model version needs checks that force its output to equal the code's result, so it adds risk and delay and no value. A model would only help if the spec needed judgement, for example turning "break into steps" into real UI structure, and that depends on the real GenUI schema. Revisit then.

## Samples (demo fallback)

`dyslexia_backend/samples/` holds saved inputs and outputs for all three calls, made with the **mock** from the **fake** findings (see `samples/README.md`). The UI can show them when no model is running. Regenerate with `python scripts/save_samples.py`.

---

## Assumptions and placeholders (everything I assumed)

**Placeholders to replace**
1. **The `analyze_text` findings shape** is my proposal. Nothing like it exists on the branch (the teammates' `analyze_html` is a rule-based dyslexia-CSS layer with no readability data).
2. **The `layout_metrics` shape** is my proposal; the tool does not exist yet.
3. **`standin_analyze_text`** is a stand-in with rough heuristics (sentence splitting on `. ! ?` before a capital; syllables estimated from vowel groups; "difficult" = 3+ syllables minus a small easy-word list; sentences over 20 words reported). Treat its numbers as approximate.
4. **The GenUI spec** is the placeholder from the brief, isolated in `adapted_ui_spec.py`.
5. **The fake findings and fake layout metrics** in `sample_data.py` and the samples are made up (flagged `FAKE_SAMPLE_DATA`). The mock's numbers (24 words, line height 1.2) are fake too.

**Design choices**
6. The model must reply with `{"recommendations": [...]}` (or `{"changes": [...]}`). A bare list, or JSON inside a markdown fence or surrounded by chatter, is also accepted.
7. The model only ever produces `status: "pending"`. I use the team's `Recommendation`, whose status can also be `accepted`, `denied` or `edited`; those are set by the UI/backend, not by the model.
8. In **mock mode** the reply is fixed and ignores the input, so checks that compare against the input (known blocks, exact quoting, numbers, facts) are skipped; the schema, unique-id and `pending` checks still run. Real-model replies get all checks.
9. Requests use `temperature: 0`. No streaming, and no JSON-mode or schema parameter is sent (the schema is in the prompt), so it works with any OpenAI-style server.
10. Retries happen only when the reply is invalid. Network errors, bad settings and HTTP errors are not retried. Default is 2 retries (3 calls); each retry resends the whole conversation and, for call 2, the image.
11. The default timeout is 120 seconds per call; the first call can be slower while Ollama loads the model.
12. **Number check:** only digits in the `rationale` are checked, against every number found anywhere in the findings (for call 2: the metrics, the guideline sentences and the applied values). Numbers written as words ("twenty-four") are not detected. `evidence` is not number-checked.
13. **Meaning check** is a proxy: digits and mid-sentence capitalised words (names, places) in `original` must still appear in `suggestion`. A model can still change meaning in ways this cannot see. The prompt forbids it, and the UI shows both texts so a person accepts or denies each change.
14. `original` must be a (whitespace-insensitive) quote from its block; otherwise the reply is rejected.
15. Page text is isolated by JSON-quoting it inside `<page_data>` tags (with `<` escaped) and by instructions in the system prompt. This reduces prompt-injection risk; it does not eliminate it.
16. Layout reference targets come from `app/guidelines.py` by import (font 18px applied, line height 1.6 applied, 65 characters, smallest heading scale), plus its rule sentences for the ranges (16 to 19 px, at least 1.5, 60 to 70 characters). If those constants change, the prompt follows.
17. A layout `block_id` may be `"page"` for page-wide advice. Screenshots must be PNG, JPEG or WebP; there is no size limit, so large images make the call slower.
18. In call 3, the plain-code version is the default and is recommended. `replace_text` carries the whole new block text, which is why it needs `blocks`. `set_style` only allows a safe list of CSS properties; later accepted styles for the same property win.
19. The model layer is English-only.

**Environment**
20. Ollama's OpenAI-compatible endpoint is `http://localhost:11434/v1` with `POST /chat/completions` and `GET /models`. Images are sent as `image_url` data URLs, which only works with an image-capable model.
21. Tried for real on the development laptop with `gemma4:e4b-it-qat` and `gemma4:e2b-it-qat` (see the timings above). Prompts were tuned after that first run (call 1 asks for at most 4 short recommendations, but e4b still returned 7; call 2 shows exact CSS formats). **Call 2 was only tested with a 1x1 white test image and fake metrics**, so how well the model reads a real screenshot is unknown. The model may use free-form `type` names (it wrote "typography" instead of "font_size"); the CSS check applies only to the types listed in `layout_recs.CSS_TYPES`.
28. **Recommendation cap:** calls 1 and 2 keep at most `max_recommendations` (default 4) recommendations, the most severe first (ties: the earlier one), in their original order, and drop the rest. This is deliberate: output length is what makes real-model calls slow. Dropped ones are counted in the log (`cap: kept 4 of 7 ... dropped 3`) but not returned, so valid findings can be lost. Pass `max_recommendations=None` for no cap. The prompt also asks for at most 4, but models do not always obey.
26. Recommendation ids are assigned by the code (`r1`, `r2`, ...), not by the model, because the model repeated ids and each repeat wasted a retry. Both calls accept `start_id`; pass `start_id=len(text_recs)+1` to the second one so ids stay unique within one analysis.
27. Gemma 4 is a thinking model, so `MODEL_REASONING_EFFORT=none` is needed for it. `reasoning_effort` is a field the OpenAI-style API allows, and Ollama accepts it; another server might ignore or reject it, in which case leave the setting unset.
22. API keys come only from environment variables; `.env` is in `.gitignore`; the smoke test never prints the key.
23. This work is on the branch `model-integration`, based on `DyslexiaBackend` (not `main`). Teammates' later changes to `app/schemas.py` are not merged; if `Recommendation` changes, re-run the tests.
24. Python 3.10+ syntax is used (`X | None`). `requirements-model.txt` is separate from the teammates' `requirements.txt` and does not need `fastmcp`.
25. Timing logs are silent unless `enable_timing_logs()` is called (the smoke test does).
