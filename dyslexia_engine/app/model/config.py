"""Model configuration, read from environment variables only (never hard-code keys).

MODEL_MOCK=1        use the built-in mock, no network, no model needed
MODEL_BASE_URL      OpenAI-compatible base URL (Ollama: http://localhost:11434/v1)
MODEL_NAME          model tag to send (required in real mode)
MODEL_API_KEY       optional; sent as a Bearer token when set
MODEL_TIMEOUT       optional request timeout in seconds (default 600; a local model on a CPU took 198 s for one call)
MODEL_REASONING_EFFORT  optional: none | low | medium | high. Sent as `reasoning_effort`. Use `none` with
                    "thinking" models such as Gemma 4, which otherwise spend minutes reasoning before answering
MODEL_MAX_RETRIES   optional; retries after an invalid reply (default 2, so up to 3 calls)

The environment is read each time `ModelConfig.from_env()` is called, not at import,
so changing a variable (or a test monkeypatching one) takes effect immediately.
"""
import os
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TIMEOUT = 600.0  # measured: gemma4:e4b on a CPU laptop needed 198 s per call, so 120 s timed out by default
DEFAULT_MAX_RETRIES = 2
_REASONING_EFFORTS = {"none", "low", "medium", "high"}
_TRUTHY = {"1", "true", "yes", "on"}


class ModelConfigError(Exception):
    """The model settings are missing or unusable."""


@dataclass(frozen=True)
class ModelConfig:
    mock: bool = False
    base_url: str = DEFAULT_BASE_URL
    model_name: str = ""
    api_key: str | None = field(default=None, repr=False)  # repr=False: keep the key out of logs
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    reasoning_effort: str | None = None
    temperature: float | None = 0.0  # None = don't send it (some models, e.g. Claude Fable, reject it)

    @classmethod
    def from_env(cls) -> "ModelConfig":
        mock = os.environ.get("MODEL_MOCK", "").strip().lower() in _TRUTHY
        try:
            timeout = float(os.environ.get("MODEL_TIMEOUT", DEFAULT_TIMEOUT))
        except ValueError:
            raise ModelConfigError("MODEL_TIMEOUT must be a number of seconds.") from None
        try:
            max_retries = int(os.environ.get("MODEL_MAX_RETRIES", DEFAULT_MAX_RETRIES))
            if max_retries < 0:
                raise ValueError
        except ValueError:
            raise ModelConfigError("MODEL_MAX_RETRIES must be a whole number, 0 or more.") from None
        effort = os.environ.get("MODEL_REASONING_EFFORT", "").strip().lower() or None
        if effort is not None and effort not in _REASONING_EFFORTS:
            raise ModelConfigError(f"MODEL_REASONING_EFFORT must be one of {sorted(_REASONING_EFFORTS)}.")
        raw_temp = os.environ.get("MODEL_TEMPERATURE", "0").strip().lower()
        try:
            temperature = None if raw_temp in ("none", "") else float(raw_temp)
        except ValueError:
            raise ModelConfigError("MODEL_TEMPERATURE must be a number, or 'none' to not send one.") from None
        return cls(
            mock=mock,
            base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
            model_name=os.environ.get("MODEL_NAME", "").strip(),
            api_key=os.environ.get("MODEL_API_KEY", "").strip() or None,
            timeout=timeout,
            max_retries=max_retries,
            reasoning_effort=effort,
            temperature=temperature,
        )

    def require_real(self) -> None:
        """Raise a clear error if real mode is selected but the settings are incomplete."""
        if not self.model_name:
            raise ModelConfigError(
                "MODEL_NAME is not set. Set it to your model tag (see `ollama list`), "
                "or set MODEL_MOCK=1 to use the mock."
            )


def load_env_file(path) -> list[str]:
    """Load MODEL_* settings from a .env file into the environment. Returns the NAMES loaded (never the values).

    Optional helper (no extra package needed). Variables that are already set win, so a value typed in the
    terminal overrides the file. Other keys in the file are ignored. A missing file is fine.
    """
    from pathlib import Path

    file = Path(path)
    if not file.is_file():
        return []
    loaded = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("\"'")
        if name.startswith("MODEL_") and value and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
