"""call_model(): the one place that talks to a model. Mock or real, chosen by config only.

Real mode sends a standard POST {MODEL_BASE_URL}/chat/completions (OpenAI format), so the same
code works with Ollama locally or RunPod later. It returns the assistant's reply as a string;
parsing and validating that string is the caller's job (see the runner).
"""
import httpx

from .config import ModelConfig
from .mock import mock_response


class ModelCallError(Exception):
    """The model could not be reached or returned an unusable HTTP response."""


def call_model(
    messages: list[dict],
    *,
    task: str,
    config: ModelConfig | None = None,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Send chat `messages` and return the reply text.

    task:      "text_recs" | "layout_recs" ... only used by the mock to pick its fixed reply.
    config:    defaults to ModelConfig.from_env().
    transport: for tests, to fake the HTTP layer without a network.
    """
    config = config or ModelConfig.from_env()
    if config.mock:
        return mock_response(task)

    config.require_real()
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    payload = {"model": config.model_name, "messages": messages, "temperature": 0}
    if config.reasoning_effort:
        payload["reasoning_effort"] = config.reasoning_effort
    try:
        with httpx.Client(timeout=config.timeout, transport=transport) as http:
            response = http.post(f"{config.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise ModelCallError(f"Model server returned HTTP {e.response.status_code}.") from None
    except httpx.HTTPError as e:
        raise ModelCallError(f"Could not reach the model at {config.base_url}: {type(e).__name__}.") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise ModelCallError("The model server's reply was not in OpenAI chat-completions format.") from None
