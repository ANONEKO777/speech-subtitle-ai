"""Test the connection to the LLM source before it is saved. Nothing here sends transcript text:
the Ollama check lists installed models, and the cloud check lists the endpoint's models with the
API key. A failure always names the URL it tried."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPException, HTTPMessage
from typing import IO, cast
from urllib.parse import urlsplit

from backend.core import notices
from backend.core.notices import Notice
from backend.manager.profiles import QWEN3_8B, runtime_set
from backend.manager.registry import Registry
from backend.manager.runtimes import runtime_executable
from backend.manager.settings import LOOPBACK, LlmSettings, LlmSource
from backend.manager.storage import Storage

TIMEOUT_S = 5.0
_BODY_BYTES = 1 << 20


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    ok: bool
    source: LlmSource
    url: str
    detail: str
    models: tuple[str, ...] = ()
    detail_notices: tuple[Notice, ...] = ()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could carry the API key to another host, so none is followed."""

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


def _get_json(url: str, key: str | None) -> object:
    handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
    if urlsplit(url).hostname in LOOPBACK:
        handlers.append(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.build_opener(*handlers).open(request, timeout=TIMEOUT_S) as response:
        return cast("object", json.loads(response.read(_BODY_BYTES).decode("utf-8")))


def _names(doc: object, list_key: str, name_key: str) -> tuple[str, ...]:
    items = cast("dict[str, object]", doc).get(list_key) if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return ()
    names: list[str] = []
    for item in cast("list[object]", items):
        value = cast("dict[str, object]", item).get(name_key) if isinstance(item, dict) else None
        if isinstance(value, str):
            names.append(value)
    return tuple(names)


def _reason(reason: object) -> Notice:
    if isinstance(reason, ConnectionRefusedError):
        return notices.LLM_TEST_REFUSED()
    if isinstance(reason, TimeoutError):
        return notices.LLM_TEST_TIMED_OUT(seconds=f"{TIMEOUT_S:g}")
    if isinstance(reason, socket.gaierror):
        return notices.LLM_TEST_HOST_NOT_FOUND()
    return notices.LLM_TEST_CANNOT_CONNECT(reason=str(reason))


def _redacted(notice: Notice, key: str | None) -> Notice:
    """`notice` with the API key taken out of its sentence and every parameter: the window gets
    both."""
    if not key:
        return notice

    def clean(value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            return value.replace(key, "***")
        return [one.replace(key, "***") for one in value]

    params = {name: clean(value) for name, value in notice.params.items()}
    return Notice(notice.code, params, notice.message.replace(key, "***"))


def _result(
    ok: bool, source: LlmSource, url: str, said: tuple[Notice, ...], models: tuple[str, ...] = ()
) -> ConnectionResult:
    return ConnectionResult(ok, source, url, said[0].message, models, said)


def _probe(
    source: LlmSource, url: str, key: str | None, list_key: str, name_key: str
) -> ConnectionResult:
    def fail(why: Notice | str) -> ConnectionResult:
        """`why` is a sentence of ours, or the words of the server or the system."""
        inside = (why,) if isinstance(why, Notice) else ()
        text = why.message if isinstance(why, Notice) else why
        said = (notices.LLM_TEST_COULD_NOT_USE(url=url, why=text), *inside)
        return _result(False, source, url, tuple(_redacted(one, key) for one in said))

    try:
        doc = _get_json(url, key)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            location = repr(exc.headers.get("Location"))
            return fail(notices.LLM_TEST_REDIRECTED(location=location))
        if exc.code in (401, 403):
            return fail(notices.LLM_TEST_KEY_REJECTED(status=str(exc.code)))
        return fail(f"HTTP {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        return fail(_reason(exc.reason))
    except (TimeoutError, OSError, HTTPException) as exc:
        return fail(f"{type(exc).__name__}: {exc}")
    except ValueError:
        return fail(notices.LLM_TEST_NOT_JSON())
    connected = (notices.LLM_TEST_CONNECTED(),)
    return _result(True, source, url, connected, _names(doc, list_key, name_key))


def _with_model(result: ConnectionResult, wanted: str) -> ConnectionResult:
    if not result.ok or not wanted:
        return result
    known = {name.removesuffix(":latest") for name in result.models}
    if wanted.removesuffix(":latest") in known:
        return result
    missing = notices.LLM_TEST_MODEL_MISSING(url=result.url, model=repr(wanted))
    return _result(False, result.source, result.url, (missing,), result.models)


def test_connection(
    llm: LlmSettings, api_key: str | None, registry: Registry, storage: Storage
) -> ConnectionResult:
    if llm.source is LlmSource.OLLAMA:
        found = _probe(LlmSource.OLLAMA, f"{llm.ollama_url}/api/tags", None, "models", "name")
        return _with_model(found, llm.ollama_model.strip())
    if llm.source is LlmSource.CLOUD:
        if not api_key:
            return _result(False, llm.source, llm.cloud_url, (notices.LLM_TEST_NO_KEY(),))
        found = _probe(LlmSource.CLOUD, f"{llm.cloud_url}/models", api_key, "data", "id")
        return _with_model(found, llm.cloud_model.strip())
    gguf = storage.model_file(registry.models[QWEN3_8B])
    server = next(
        (
            p
            for rid in dict.fromkeys((runtime_set().llama, runtime_set().llama_cpu))
            if (p := runtime_executable(rid, registry, storage))
        ),
        None,
    )
    missing = [
        name
        for name, path in (("llama-server", server), (QWEN3_8B, gguf))
        if not path or not path.is_file()
    ]
    where = str(server or storage.runtimes_root)
    if missing:
        return _result(False, llm.source, where, (notices.LLM_TEST_NOT_INSTALLED(missing=missing),))
    return _result(True, llm.source, where, (notices.LLM_TEST_BUILTIN_READY(),))
