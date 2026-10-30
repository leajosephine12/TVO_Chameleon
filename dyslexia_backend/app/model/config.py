"""Model configuration, read from environment variables only (never hard-code keys).

MODEL_MOCK=1        use the built-in mock, no network, no model needed
MODEL_BASE_URL      OpenAI-compatible base URL (Ollama: http://localhost:11434/v1)
MODEL_NAME          model tag to send (required in real mode)
MODEL_API_KEY       optional; sent as a Bearer token when set
MODEL_TIMEOUT       optional request timeout in seconds (default 120)

The environment is read each time `ModelConfig.from_env()` is called, not at import,
so changing a variable (or a test monkeypatching one) takes effect immediately.
"""
import os
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TIMEOUT = 120.0
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

    @classmethod
    def from_env(cls) -> "ModelConfig":
        mock = os.environ.get("MODEL_MOCK", "").strip().lower() in _TRUTHY
        try:
            timeout = float(os.environ.get("MODEL_TIMEOUT", DEFAULT_TIMEOUT))
        except ValueError:
            raise ModelConfigError("MODEL_TIMEOUT must be a number of seconds.") from None
        return cls(
            mock=mock,
            base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
            model_name=os.environ.get("MODEL_NAME", "").strip(),
            api_key=os.environ.get("MODEL_API_KEY", "").strip() or None,
            timeout=timeout,
        )

    def require_real(self) -> None:
        """Raise a clear error if real mode is selected but the settings are incomplete."""
        if not self.model_name:
            raise ModelConfigError(
                "MODEL_NAME is not set. Set it to your model tag (see `ollama list`), "
                "or set MODEL_MOCK=1 to use the mock."
            )
