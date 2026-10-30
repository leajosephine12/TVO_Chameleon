"""Shared loop for every model call: ask, parse, validate, retry with the error fed back.

If the model still fails after the retries, ModelOutputError is raised. Invalid data is never returned.
"""
import json
import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .client import call_model
from .config import ModelConfig
from .guards import extract_json
from .schemas import Recommendation, RecommendationList

log = logging.getLogger("app.model")
T = TypeVar("T", bound=BaseModel)
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
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport: httpx.BaseTransport | None = None,
    caller: Callable[..., str] = call_model,
) -> T:
    """Return a validated `schema` object, or raise ModelOutputError. Network/config errors are not retried.

    max_retries defaults to MODEL_MAX_RETRIES (2). Each attempt's duration is logged to the "app.model" logger.
    """
    config = config or ModelConfig.from_env()
    if max_retries is None:
        max_retries = config.max_retries
    messages = list(messages)
    attempts = max_retries + 1
    problems: list[str] = []
    started = time.perf_counter()
    for n in range(1, attempts + 1):
        label = f"task={task} attempt={n}/{attempts} retry={n > 1}"
        t0 = time.perf_counter()
        try:
            reply = caller(messages, task=task, config=config, transport=transport)
        except Exception as e:
            log.warning("%s model_call=%.2fs outcome=call_failed (%s)", label, time.perf_counter() - t0, type(e).__name__)
            raise
        call_secs = time.perf_counter() - t0
        problems = []
        parsed = None
        try:
            raw = extract_json(reply)
            if isinstance(raw, list) and len(schema.model_fields) == 1:  # small models often drop the wrapper object
                raw = {next(iter(schema.model_fields)): raw}
            parsed = schema.model_validate(raw)
        except json.JSONDecodeError as e:
            problems = [f"The reply was not valid JSON ({e.msg} at position {e.pos})."]
        except ValidationError as e:
            problems = _describe_validation_error(e)
        if parsed is not None:
            problems = [p for check in checks for p in check(parsed)]
            if not problems:
                log.info("%s model_call=%.2fs outcome=ok total=%.2fs", label, call_secs, time.perf_counter() - started)
                return parsed
        log.info("%s model_call=%.2fs outcome=invalid (%d problem%s)", label, call_secs, len(problems), "" if len(problems) == 1 else "s")
        for problem in problems[:3]:
            log.info("    rejected because: %s", problem[:300])
        messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": _feedback(problems)}]
    log.warning("task=%s gave up after %d attempts, total=%.2fs", task, attempts, time.perf_counter() - started)
    raise ModelOutputError(task, attempts, problems)


def run_recommendation_task(
    *,
    checks: tuple[Callable[[list[Recommendation]], list[str]], ...] = (),
    **kwargs,
) -> list[Recommendation]:
    """Like run_task for calls 1 and 2, but returns a plain list[Recommendation] (the wrapper is removed here)."""
    wrapped = tuple((lambda parsed, c=c: c(parsed.recommendations)) for c in checks)
    return run_task(schema=RecommendationList, checks=wrapped, **kwargs).recommendations


def renumber(recs: list[Recommendation], start: int = 1) -> list[Recommendation]:
    """Give recommendations ids r{start}, r{start+1}, ... The code, not the model, owns ids (models repeat them)."""
    return [r.model_copy(update={"id": f"r{start + i}"}) for i, r in enumerate(recs)]
