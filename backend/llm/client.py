from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email.message import Message as EmailMessage
from http.client import HTTPException, HTTPMessage
from typing import IO, Literal, TypedDict, cast
from urllib.parse import urlsplit

from backend.core import notices
from backend.core.notices import Template, noticed

DEFAULT_TIMEOUT_S = 600.0
LLM_SEED = 20261105
"""Sent with every request, so a retry at a positive temperature draws the same tokens each run."""
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ERROR_BODY_BYTES = 4096
_ERROR_DETAIL_CHARS = 500
_KEY_PREFIX_CHARS = 8
"""A key cut this short or shorter at the end of a cut body is not redacted."""
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
        if not all("!" <= char <= "~" for char in self.api_key):
            raise noticed(ValueError, notices.LLM_KEY_UNSENDABLE())
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
    try:
        doc = cast("object", json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(
            config, notices.LLM_REPLY_NOT_JSON, url=config.chat_url, error=str(exc)
        ) from exc
    content = _member(_member(_first(_member(doc, "choices")), "message"), "content")
    if not isinstance(content, str):
        raise _fail(config, notices.LLM_REPLY_NO_CONTENT, url=config.chat_url)
    return content


def _spellings(char: str) -> str:
    """Each way a server can echo one character of a key: as it is, percent-encoded, JSON-escaped
    or as an HTML entity. Hex digits match in either case, as servers write both, and a JSON
    escape may come with its backslash doubled, as `repr` of the text writes it."""
    code = ord(char)
    escaped = [r"\\+/"] if char == "/" else []
    forms = [
        re.escape(char),
        *escaped,
        f"%{code:02x}",
        rf"\\+u{code:04x}",
        f"&#{code};",
        f"&#x0*{code:x};",
    ]
    return "(?:" + "|".join(forms) + ")"


def _key_pattern(key: str, *, cut: bool) -> re.Pattern[str]:
    """The key in any mix of the spellings a server echoes. With `cut`, also any prefix of at
    least `_KEY_PREFIX_CHARS` characters that ends the text, where a body was cut off."""
    chars = [_spellings(char) for char in key]
    whole = "".join(chars)
    if not cut or len(key) <= _KEY_PREFIX_CHARS:
        return re.compile(whole, re.IGNORECASE)
    rest = ""
    for char in reversed(chars[_KEY_PREFIX_CHARS:]):
        rest = f"(?:{char}{rest})?"
    prefix = "".join(chars[:_KEY_PREFIX_CHARS]) + rest + r"\Z"
    return re.compile(f"{whole}|{prefix}", re.IGNORECASE)


def redact(key: str, text: str, *, cut: bool = False) -> str:
    """`text` with every echo of `key` replaced by `***`. `cut` says the text was cut off, so a
    piece of the key at its end goes too."""
    return _key_pattern(key, cut=cut).sub("***", text) if key else text


def _redact(config: LlmConfig, text: str) -> str:
    return redact(config.api_key, text)


def _fail(
    config: LlmConfig,
    sentence: Template,
    *,
    retryable: bool = False,
    retry_after_s: float | None = None,
    **params: str,
) -> LlmError:
    """The error that says `sentence`. The window gets the parameters beside the text, so the key
    is taken out of each of them, not only out of the sentence they make."""
    said = sentence(**{name: _redact(config, value) for name, value in params.items()})

    def error(message: str) -> LlmError:
        return LlmError(message, retryable=retryable, retry_after_s=retry_after_s)

    return noticed(error, said)


def _retry_after(headers: EmailMessage) -> float | None:
    value = (headers.get("Retry-After") or "").strip()
    return float(value) if value.isdigit() else None


def _http_error(exc: urllib.error.HTTPError, config: LlmConfig) -> LlmError:
    body = exc.read(_ERROR_BODY_BYTES).decode("utf-8", errors="replace")
    detail = redact(config.api_key, body, cut=True)
    detail = detail.strip()[:_ERROR_DETAIL_CHARS]
    return _fail(
        config,
        notices.LLM_HTTP,
        retryable=exc.code in _RETRYABLE_STATUS,
        retry_after_s=_retry_after(exc.headers),
        url=config.chat_url,
        status=f"{exc.code} {exc.reason}",
        detail=detail,
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
                notices.LLM_REDIRECTED,
                url=config.chat_url,
                location=repr(exc.headers.get("Location")),
            ) from exc
        raise _http_error(exc, config) from exc
    except (urllib.error.URLError, OSError, HTTPException) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        retryable = _transient(reason)
        if isinstance(reason, TimeoutError):
            raise _fail(
                config,
                notices.LLM_TIMED_OUT,
                retryable=retryable,
                url=config.base_url,
                seconds=f"{config.timeout_s:g}",
            ) from exc
        raise _fail(
            config,
            notices.LLM_UNREACHABLE,
            retryable=retryable,
            url=config.base_url,
            reason=str(reason),
        ) from exc
    return _reply_text(raw, config)
