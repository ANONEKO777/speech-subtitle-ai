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


def _reason(reason: object) -> str:
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused, nothing is listening at that address"
    if isinstance(reason, TimeoutError):
        return f"no answer within {TIMEOUT_S:g} s"
    if isinstance(reason, socket.gaierror):
        return "the host name was not found"
    return f"cannot connect ({reason})"


def _probe(
    source: LlmSource, url: str, key: str | None, list_key: str, name_key: str
) -> ConnectionResult:
    def fail(why: str) -> ConnectionResult:
        message = f"could not use {url}: {why}"
        return ConnectionResult(False, source, url, message.replace(key, "***") if key else message)

    try:
        doc = _get_json(url, key)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            return fail(
                f"it redirected to {exc.headers.get('Location')!r}; redirects are not followed"
            )
        if exc.code in (401, 403):
            return fail(f"the server rejected the API key (HTTP {exc.code})")
        return fail(f"HTTP {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        return fail(_reason(exc.reason))
    except (TimeoutError, OSError, HTTPException) as exc:
        return fail(f"{type(exc).__name__}: {exc}")
    except ValueError:
        return fail("the answer is not JSON, so this is not that kind of server")
    return ConnectionResult(True, source, url, "connected", _names(doc, list_key, name_key))


def _with_model(result: ConnectionResult, wanted: str) -> ConnectionResult:
    if not result.ok or not wanted:
        return result
    known = {name.removesuffix(":latest") for name in result.models}
    if wanted.removesuffix(":latest") in known:
        return result
    return ConnectionResult(
        False,
        result.source,
        result.url,
        f"connected to {result.url}, but model {wanted!r} is not installed there",
        result.models,
    )


def test_connection(
    llm: LlmSettings, api_key: str | None, registry: Registry, storage: Storage
) -> ConnectionResult:
    if llm.source is LlmSource.OLLAMA:
        found = _probe(LlmSource.OLLAMA, f"{llm.ollama_url}/api/tags", None, "models", "name")
        return _with_model(found, llm.ollama_model.strip())
    if llm.source is LlmSource.CLOUD:
        if not api_key:
            return ConnectionResult(
                False,
                llm.source,
                llm.cloud_url,
                "no API key to test with: enter the key for this address",
            )
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
        return ConnectionResult(False, llm.source, where, f"not installed: {', '.join(missing)}")
    return ConnectionResult(True, llm.source, where, "llama-server and the model are installed")
