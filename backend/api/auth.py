"""The trust boundary of the local service.

Every request passes `Guard` before any route sees it, including the routers mounted from other
modules, so no route can forget to check. Three checks run in order. `Host` must be one the service
listens on, which stops DNS rebinding. `Origin`, when a browser sends one, must be an app origin,
so a web page cannot make the user's browser call the service. The token must match, which stops
every other program on the machine. A rejected request never reaches a route.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send

APP_ORIGINS = frozenset(
    {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
    }
)
_EVENTS_PATH = re.compile(r"/api/jobs/[^/]+/events")
_ALLOWED_HEADERS = "authorization, content-type, last-event-id"
_ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS"


def new_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class GuardConfig:
    token: str
    hosts: frozenset[str]
    origins: frozenset[str] = APP_ORIGINS

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("token is empty")


def local_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def _deny(status: int, detail: str, extra: Iterable[tuple[bytes, bytes]] = ()) -> Message:
    return {
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"cache-control", b"no-store"),
            *extra,
        ],
    }


class Guard:
    def __init__(self, app: ASGIApp, config: GuardConfig) -> None:
        self.app, self.config = app, config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await _reject(send, 403, "only http requests are served")
            return
        headers = _headers(scope)
        if headers.get("host") not in self.config.hosts:
            await _reject(send, 403, "host not allowed")
            return
        origin = headers.get("origin")
        if origin is not None and origin not in self.config.origins:
            await _reject(send, 403, "origin not allowed")
            return
        if origin is not None and _is_preflight(scope, headers):
            await _preflight(send, origin)
            return
        if not self._token_ok(scope, headers):
            await _reject(send, 401, "missing or wrong token", bearer=True)
            return
        if origin is None:
            await self.app(scope, receive, send)
            return

        async def with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"vary", b"origin"),
                ]
            await send(message)

        await self.app(scope, receive, with_cors)

    def _token_ok(self, scope: Scope, headers: Mapping[str, str]) -> bool:
        match headers.get("authorization", "").split(maxsplit=1):
            case [scheme, given] if scheme.lower() == "bearer":
                return self._same(given)
            case _:
                pass
        if scope["method"] == "GET" and _EVENTS_PATH.fullmatch(scope["path"]):
            query = parse_qs(scope["query_string"].decode("latin-1"))
            return any(self._same(given) for given in query.get("token", ()))
        return False

    def _same(self, given: str) -> bool:
        return hmac.compare_digest(given.encode("utf-8"), self.config.token.encode("utf-8"))


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}


def _is_preflight(scope: Scope, headers: Mapping[str, str]) -> bool:
    return scope["method"] == "OPTIONS" and "access-control-request-method" in headers


async def _reject(send: Send, status: int, detail: str, *, bearer: bool = False) -> None:
    extra = [(b"www-authenticate", b"Bearer")] if bearer else []
    await send(_deny(status, detail, extra))
    await send({"type": "http.response.body", "body": json.dumps({"detail": detail}).encode()})


async def _preflight(send: Send, origin: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 204,
            "headers": [
                (b"access-control-allow-origin", origin.encode("latin-1")),
                (b"access-control-allow-methods", _ALLOWED_METHODS.encode()),
                (b"access-control-allow-headers", _ALLOWED_HEADERS.encode()),
                (b"access-control-max-age", b"600"),
                (b"vary", b"origin"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})
