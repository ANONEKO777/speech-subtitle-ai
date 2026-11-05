from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import TypeVar, cast

from backend.llm import client
from backend.llm.client import LlmConfig, LlmError, Message

log = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 3
RETRY_TEMPERATURE = 0.3
MAX_BACKOFF_S = 60.0

ChatFn = Callable[[Sequence[Message], float], str]

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"\A\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*\Z", re.DOTALL)


class ReplyError(ValueError):
    """The model answered, but the reply is not usable for what was asked."""


class RepliesRejected(Exception):
    """Every attempt got an answer that failed validation, or a server error after one that did."""

    def __init__(self, reason: str, attempts: int) -> None:
        super().__init__(f"{attempts} attempts: {reason}")
        self.reason = reason
        self.attempts = attempts


def json_chat(config: LlmConfig, max_tokens: int | None = None) -> ChatFn:
    """The `ChatFn` for an OpenAI-compatible endpoint, asking for a JSON object back of at most
    `max_tokens` tokens."""

    def chat(messages: Sequence[Message], temperature: float) -> str:
        return client.chat(
            config, messages, temperature=temperature, json_mode=True, max_tokens=max_tokens
        )

    return chat


def parse_json_reply(text: str) -> object:
    """The JSON value in a reply, after dropping a `<think>` block and a code fence."""
    text = _THINK.sub("", text).strip()
    fenced = _FENCE.match(text)
    try:
        return cast("object", json.loads(fenced.group(1) if fenced else text))
    except json.JSONDecodeError as exc:
        raise ReplyError(f"the reply is not valid JSON ({exc})") from exc


def ask(
    chat: ChatFn,
    messages: Sequence[Message],
    parse: Callable[[str], T],
    *,
    reprompt: Callable[[str], str],
    label: str,
    retries: int = MAX_RETRIES,
    echo_limit: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Ask until `parse` accepts a reply, returning its value and the attempt that succeeded.

    A reply that `parse` rejects with `ReplyError` is sent back with `reprompt(reason)`. A
    retryable `LlmError` waits (`Retry-After` capped at `MAX_BACKOFF_S`) and asks again. A
    non-retryable one raises at once, as does a server that failed every attempt. Otherwise
    `RepliesRejected` says why the last answer failed. A rejected reply longer than `echo_limit`
    characters is not sent back, only the reason, so a runaway reply cannot push the retry over
    the context.
    """
    attempts = retries + 1
    sent: list[Message] = list(messages)
    reason = ""
    server_error: LlmError | None = None
    answered = False
    for attempt in range(1, attempts + 1):
        try:
            text = chat(sent, 0.0 if attempt == 1 else RETRY_TEMPERATURE)
        except LlmError as exc:
            if not exc.retryable:
                raise
            reason, server_error = str(exc), exc
            log.warning("%s attempt %d failed: %s", label, attempt, reason)
            delay = min(2.0 ** (attempt - 1), 8.0)
            if exc.retry_after_s is not None:
                delay = min(max(delay, exc.retry_after_s), MAX_BACKOFF_S)
            sleep(delay)
            continue
        answered = True
        try:
            return parse(text), attempt
        except ReplyError as exc:
            reason = str(exc)
            log.warning("%s attempt %d rejected: %s", label, attempt, reason)
            echoed = echo_limit is None or len(text) <= echo_limit
            sent = [
                *messages,
                *([Message(role="assistant", content=text)] if echoed else []),
                Message(role="user", content=reprompt(reason)),
            ]
    if server_error and not answered:
        raise server_error
    raise RepliesRejected(reason, attempts)
