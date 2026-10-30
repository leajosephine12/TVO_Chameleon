"""Shared loop for every model call: ask, parse, validate, retry with the error fed back.

If the model still fails after the retries, ModelOutputError is raised. Invalid data is never returned.
"""
import json
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .client import call_model
from .config import ModelConfig
from .guards import extract_json
from .schemas import Recommendation, RecommendationList

T = TypeVar("T", bound=BaseModel)
DEFAULT_MAX_RETRIES = 2
_MAX_PROBLEMS_SHOWN = 10


class ModelOutputError(Exception):
    """The model never produced valid output. `problems` lists what was wrong on the last attempt."""

    def __init__(self, task: str, attempts: int, problems: list[str]):
        self.task, self.attempts, self.problems = task, attempts, problems
        super().__init__(f"Model output for '{task}' was still invalid after {attempts} attempts: " + "; ".join(problems[:3]))


def _describe_validation_error(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc']) or 'reply'}: {err['msg']}" for err in e.errors()[:_MAX_PROBLEMS_SHOWN]]


def _feedback(problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems[:_MAX_PROBLEMS_SHOWN])
    return f"Your previous reply was rejected:\n{listed}\nReply again with ONLY the corrected JSON object."


def run_task(
    *,
    task: str,
    messages: list[dict],
    schema: type[T],
    checks: tuple[Callable[[T], list[str]], ...] = (),
    max_retries: int = DEFAULT_MAX_RETRIES,
    config: ModelConfig | None = None,
    transport: httpx.BaseTransport | None = None,
    caller: Callable[..., str] = call_model,
) -> T:
    """Return a validated `schema` object, or raise ModelOutputError. Network/config errors are not retried."""
    messages = list(messages)
    attempts = max_retries + 1
    problems: list[str] = []
    for _ in range(attempts):
        reply = caller(messages, task=task, config=config, transport=transport)
        problems = []
        parsed = None
        try:
            raw = extract_json(reply)
            if isinstance(raw, list):  # small models often drop the wrapper object; accept a bare list
                raw = {"recommendations": raw}
            parsed = schema.model_validate(raw)
        except json.JSONDecodeError as e:
            problems = [f"The reply was not valid JSON ({e.msg} at position {e.pos})."]
        except ValidationError as e:
            problems = _describe_validation_error(e)
        if parsed is not None:
            problems = [p for check in checks for p in check(parsed)]
            if not problems:
                return parsed
        messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": _feedback(problems)}]
    raise ModelOutputError(task, attempts, problems)


def run_recommendation_task(
    *,
    checks: tuple[Callable[[list[Recommendation]], list[str]], ...] = (),
    **kwargs,
) -> list[Recommendation]:
    """Like run_task for calls 1 and 2, but returns a plain list[Recommendation] (the wrapper is removed here)."""
    wrapped = tuple((lambda parsed, c=c: c(parsed.recommendations)) for c in checks)
    return run_task(schema=RecommendationList, checks=wrapped, **kwargs).recommendations
