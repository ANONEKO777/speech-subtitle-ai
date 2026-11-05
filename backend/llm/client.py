from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email.message import Message as EmailMessage
from http.client import HTTPException, HTTPMessage
from typing import IO, Literal, TypedDict, cast
from urllib.parse import urlsplit

DEFAULT_TIMEOUT_S = 600.0
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ERROR_BODY_BYTES = 4096
_ERROR_DETAIL_CHARS = 500
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LlmError(Exception):
    """The LLM endpoint could not give an answer. `retryable` says if asking again can help."""

    def __init__(
        self, message: str, *, retryable: bool = False, retry_after_s: float | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_s = retry_after_s


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Where and how to reach an OpenAI-compatible chat endpoint.

    `extra_body` is merged into every request body, for server-specific switches such as
    llama-server's `chat_template_kwargs`.
    """

    base_url: str
    model: str
    api_key: str = field(default="", repr=False)
    extra_body: Mapping[str, object] = field(default_factory=dict[str, object])
    timeout_s: float = DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        parts = urlsplit(self.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("base_url must be an http(s) URL with a host")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError(
                "base_url must not hold a user name, password, query or fragment; "
                "pass the key as api_key"
            )
        if self.api_key and parts.scheme == "http" and not self.is_local:
            raise ValueError(
                f"refusing to send an API key over plain http to {parts.hostname}; use https"
            )
        if not self.model:
            raise ValueError("model is empty")

    @property
    def is_local(self) -> bool:
        return urlsplit(self.base_url).hostname in _LOOPBACK_HOSTS

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _opener(config: LlmConfig) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
    if config.is_local:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _request_body(
    config: LlmConfig,
    messages: Sequence[Message],
    temperature: float,
    json_mode: bool,
    max_tokens: int | None,
) -> bytes:
    body: dict[str, object] = {
        **config.extra_body,
        "model": config.model,
        "messages": list(messages),
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _member(value: object, key: str) -> object:
    return cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None


def _first(value: object) -> object:
    return cast("list[object]", value)[0] if isinstance(value, list) and value else None


def _reply_text(raw: bytes, config: LlmConfig) -> str:
    where = f"{config.chat_url} did not return a chat completion"
    try:
        doc = cast("object", json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LlmError(f"{where}: body is not JSON ({exc})") from exc
    content = _member(_member(_first(_member(doc, "choices")), "message"), "content")
    if not isinstance(content, str):
        raise LlmError(f"{where}: no choices[0].message.content string")
    return content


def _redact(config: LlmConfig, text: str) -> str:
    return text.replace(config.api_key, "***") if config.api_key else text


def _fail(
    config: LlmConfig, message: str, *, retryable: bool = False, retry_after_s: float | None = None
) -> LlmError:
    return LlmError(_redact(config, message), retryable=retryable, retry_after_s=retry_after_s)


def _retry_after(headers: EmailMessage) -> float | None:
    value = (headers.get("Retry-After") or "").strip()
    return float(value) if value.isdigit() else None


def _http_error(exc: urllib.error.HTTPError, config: LlmConfig) -> LlmError:
    detail = _redact(config, exc.read(_ERROR_BODY_BYTES).decode("utf-8", errors="replace"))
    detail = detail.strip()[:_ERROR_DETAIL_CHARS]
    return _fail(
        config,
        f"{config.chat_url} answered HTTP {exc.code} {exc.reason}: {detail}",
        retryable=exc.code in _RETRYABLE_STATUS,
        retry_after_s=_retry_after(exc.headers),
    )


def _transient(reason: object) -> bool:
    if isinstance(reason, ConnectionRefusedError):
        return False
    return isinstance(reason, TimeoutError | ConnectionError | HTTPException)


def chat(
    config: LlmConfig,
    messages: Sequence[Message],
    *,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> str:
    request = urllib.request.Request(
        config.chat_url,
        data=_request_body(config, messages, temperature, json_mode, max_tokens),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}),
        },
        method="POST",
    )
    try:
        with _opener(config).open(request, timeout=config.timeout_s) as response:
            raw = cast("bytes", response.read())
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise _fail(
                config,
                f"{config.chat_url} redirected to {exc.headers.get('Location')!r}; "
                "redirects are not followed",
            ) from exc
        raise _http_error(exc, config) from exc
    except (urllib.error.URLError, OSError, HTTPException) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        if isinstance(reason, TimeoutError):
            message = f"no answer from {config.base_url} within {config.timeout_s:g} s"
        else:
            message = f"cannot reach the LLM server at {config.base_url}: {reason}"
        raise _fail(config, message, retryable=_transient(reason)) from exc
    return _reply_text(raw, config)
