"""Smoke test: send one tiny request to the configured model and print the reply and how long it took.

Run from the dyslexia_backend folder:
    python scripts/smoke_test.py             # one tiny request
    python scripts/smoke_test.py --full      # also run call 1 on the two TVO sample paragraphs (validation + retries)
    python scripts/smoke_test.py --vision    # also run call 2 with a tiny test image (needs a vision-capable model)

Mode comes from the environment (or a .env file): MODEL_MOCK=1 uses the mock, otherwise MODEL_BASE_URL and MODEL_NAME
pick the real model. Per-attempt timing is printed as log lines. Exit code 0 = worked, 1 = failed (the reason is printed).
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.model.client import ModelCallError, call_model  # noqa: E402
from app.model.config import ModelConfig, ModelConfigError, load_env_file  # noqa: E402
from app.model.layout_recs import generate_layout_recommendations  # noqa: E402
from app.model.log import enable_timing_logs  # noqa: E402
from app.model.runner import ModelOutputError  # noqa: E402
from app.model.sample_data import FAKE_LAYOUT_METRICS, SAMPLE_BLOCKS, TINY_PNG  # noqa: E402
from app.model.standin_analyze_text import standin_analyze_text  # noqa: E402
from app.model.text_recs import generate_text_recommendations  # noqa: E402

TINY_REQUEST = [{"role": "user", "content": "Reply with the single word: pong"}]


def available_models(config: ModelConfig) -> list[str] | None:
    """Ask the server which models it has (GET {base_url}/models). None if it cannot say."""
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    try:
        reply = httpx.get(f"{config.base_url}/models", headers=headers, timeout=min(config.timeout, 10))
        reply.raise_for_status()
        return [m["id"] for m in reply.json()["data"]]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def timed(label: str, fn):
    start = time.perf_counter()
    result = fn()
    print(f"  -> {label} took {time.perf_counter() - start:.2f} seconds")
    return result


def show(recs) -> None:
    for r in recs:
        print(f"  [{r.id}] {r.block_id} {r.type} ({r.severity}): {r.rationale}")
        print(f"        before: {r.original[:90]}")
        print(f"        after:  {r.suggestion[:90]}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="also run call 1 (text recommendations)")
    parser.add_argument("--vision", action="store_true", help="also run call 2 (layout, sends a tiny image)")
    parser.add_argument("--env-file", default=str(ROOT / ".env"), help="optional .env file (default: dyslexia_backend/.env)")
    args = parser.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    loaded = load_env_file(args.env_file)
    enable_timing_logs()
    try:
        config = ModelConfig.from_env()
        print(f"Mode:     {'MOCK (fixed replies, no model is used)' if config.mock else 'REAL model'}")
        if loaded:
            print(f"Settings: loaded {', '.join(loaded)} from {args.env_file}")
        if not config.mock:
            config.require_real()
            print(f"Server:   {config.base_url}")
            print(f"Model:    {config.model_name}   (API key set: {'yes' if config.api_key else 'no'})")
            models = available_models(config)
            if models is None:
                print("Models:   could not list the server's models (the server may not support it, or it is not running)")
            else:
                print(f"Models:   {', '.join(models) or '(none installed)'}")
                if config.model_name not in models:
                    print(f"WARNING:  '{config.model_name}' is not in that list. Check the spelling against `ollama list`.")

        print("\n1. Tiny request")
        reply = timed("the request", lambda: call_model(TINY_REQUEST, task="text_recs", config=config))
        print(f"  reply: {reply[:300]}{'...' if len(reply) > 300 else ''}")
        if config.mock:
            print("  (this is the mock's fixed reply, so it does not answer the question)")

        if args.full:
            print("\n2. Call 1 on the two TVO sample paragraphs (stand-in findings)")
            show(timed("call 1 including any retries", lambda: generate_text_recommendations(
                SAMPLE_BLOCKS, standin_analyze_text(SAMPLE_BLOCKS), config=config)))
        if args.vision:
            print("\n3. Call 2 with a tiny test image and FAKE layout metrics")
            show(timed("call 2 including any retries", lambda: generate_layout_recommendations(
                TINY_PNG, FAKE_LAYOUT_METRICS, config=config)))
    except ModelConfigError as e:
        print(f"\nFAILED (settings): {e}")
        return 1
    except ModelCallError as e:
        print(f"\nFAILED (could not get a reply): {e}")
        return 1
    except ModelOutputError as e:
        print(f"\nFAILED (the model replied, but never with valid output): {e}")
        for problem in e.problems[:5]:
            print(f"  - {problem}")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
