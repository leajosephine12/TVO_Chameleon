import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.model.config import load_env_file

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "smoke_test.py"


def smoke(*args, **env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("MODEL_")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(BACKEND_DIR / "no-such.env"), *args],
        cwd=BACKEND_DIR, env=clean | env, capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout + result.stderr


# ---- smoke test script ----

def test_smoke_test_works_in_mock_mode():
    code, out = smoke(MODEL_MOCK="1")
    assert code == 0 and "MOCK" in out and "took" in out and out.strip().endswith("OK")


def test_smoke_test_full_and_vision_in_mock_mode_with_timing_logs():
    code, out = smoke("--full", "--vision", MODEL_MOCK="1")
    assert code == 0 and "[r1]" in out and "[r3]" in out
    assert "attempt=1/3 retry=False" in out and "outcome=ok" in out  # per-attempt timing is shown


def test_real_mode_without_a_model_name_explains_what_to_do():
    code, out = smoke()
    assert code == 1 and "MODEL_NAME" in out and "MODEL_MOCK=1" in out


def test_real_mode_with_nothing_listening_gives_a_clear_failure():
    code, out = smoke(MODEL_NAME="x", MODEL_BASE_URL="http://127.0.0.1:9/v1", MODEL_TIMEOUT="1")
    assert code == 1 and "Could not reach" in out and "Traceback" not in out


def test_the_api_key_is_never_printed():
    code, out = smoke(MODEL_NAME="x", MODEL_BASE_URL="http://127.0.0.1:9/v1", MODEL_API_KEY="sk-super-secret", MODEL_TIMEOUT="1")
    assert "sk-super-secret" not in out and "API key set: yes" in out


# ---- .env loading ----

@pytest.fixture
def clean_env(monkeypatch):
    for k in ("MODEL_MOCK", "MODEL_NAME", "MODEL_BASE_URL", "MODEL_API_KEY", "OTHER_THING"):
        monkeypatch.delenv(k, raising=False)


def test_load_env_file(tmp_path, monkeypatch, clean_env):
    f = tmp_path / ".env"
    f.write_text('# comment\n\nMODEL_NAME="my-model"\nMODEL_BASE_URL=http://x/v1\nOTHER_THING=nope\nMODEL_API_KEY=\n', encoding="utf-8")
    assert load_env_file(f) == ["MODEL_NAME", "MODEL_BASE_URL"]  # names only; empty values and non-MODEL_ keys skipped
    assert os.environ["MODEL_NAME"] == "my-model" and "OTHER_THING" not in os.environ
    monkeypatch.delenv("MODEL_NAME"); monkeypatch.delenv("MODEL_BASE_URL")


def test_terminal_value_beats_the_file(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("MODEL_NAME", "from-terminal")
    f = tmp_path / ".env"
    f.write_text("MODEL_NAME=from-file\n", encoding="utf-8")
    assert load_env_file(f) == [] and os.environ["MODEL_NAME"] == "from-terminal"


def test_missing_env_file_is_fine(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == []


def test_example_file_lists_every_setting():
    text = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    for name in ("MODEL_MOCK", "MODEL_BASE_URL", "MODEL_NAME", "MODEL_API_KEY", "MODEL_TIMEOUT", "MODEL_MAX_RETRIES"):
        assert name in text
    assert "sk-" not in text
