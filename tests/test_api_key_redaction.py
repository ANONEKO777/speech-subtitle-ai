"""No spelling of the API key reaches what the window, the log or a stored file can show. Every key
here is invented."""

from __future__ import annotations

import contextlib
import html
import io
import json
import urllib.error
import urllib.parse
from email.message import Message
from types import SimpleNamespace

import pytest
from manage_support import Rig

from backend.core.notices import notices_of, to_json
from backend.llm import client
from backend.llm.ask import ask, json_chat, parse_json_reply
from backend.llm.client import LlmConfig, LlmError
from backend.manager import llm_check
from backend.manager.settings import LlmSource

KEY = "sk-INV+ented/Key==9988776655443322"
"""Holds the characters a URL or JSON spells differently: `+`, `/` and `=`."""

SPELLINGS = {
    "as sent": KEY,
    "URL-encoded": urllib.parse.quote(KEY, safe=""),
    "URL-encoded in lower case": urllib.parse.quote(KEY, safe="").lower(),
    "form-encoded": urllib.parse.quote_plus(KEY),
    "JSON with an escaped slash": json.dumps(KEY).replace("/", "\\/")[1:-1],
    "JSON as ASCII escapes": "".join(f"\\u{ord(c):04x}" for c in KEY),
    "HTML": html.escape(KEY),
    "HTML entities": "".join(f"&#{ord(c)};" for c in KEY),
}


def _shown(exc: BaseException) -> str:
    """Everything the window can get from a failure: its text and the notices beside it."""
    return str(exc) + json.dumps(to_json(notices_of(exc)))


def _answering(monkeypatch: pytest.MonkeyPatch, answer: Exception) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise answer

    def opener(_config: LlmConfig) -> object:
        return SimpleNamespace(open=refuse)

    monkeypatch.setattr(client, "_opener", opener)


def _chat_failure(monkeypatch: pytest.MonkeyPatch, config: LlmConfig, answer: Exception) -> str:
    _answering(monkeypatch, answer)
    with pytest.raises(LlmError) as caught:
        client.chat(config, [{"role": "user", "content": "hi"}])
    return _shown(caught.value)


def _no_piece_of(key: str, shown: str) -> None:
    pieces = {key[i : i + 8] for i in range(len(key) - 7)}
    assert not [piece for piece in pieces if piece in shown], shown


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_a_server_that_echoes_the_key_in_any_spelling_shows_none_of_it(
    monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    config = LlmConfig("https://api.example.test/v1", "m", KEY)
    echoed = SPELLINGS[spelling]
    moved = Message()
    moved["Location"] = f"https://api.example.test/?key={echoed}"
    for answer in (
        urllib.error.HTTPError(config.chat_url, 401, echoed, Message(), io.BytesIO()),
        urllib.error.HTTPError(config.chat_url, 400, "Bad", Message(), io.BytesIO(echoed.encode())),
        urllib.error.HTTPError(config.chat_url, 302, "Found", moved, io.BytesIO()),
        urllib.error.URLError(f"proxy refused {echoed}"),
    ):
        shown = _chat_failure(monkeypatch, config, answer)

        assert echoed not in shown and "***" in shown, shown
        _no_piece_of(KEY, shown)


def test_a_body_cut_inside_the_key_shows_no_piece_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    config = LlmConfig("https://api.example.test/v1", "m", KEY)
    for kept in (8, 20, len(KEY) - 1):
        body = (" " * (4096 - kept) + KEY + " tail").encode()
        answer = urllib.error.HTTPError(config.chat_url, 400, "Bad", Message(), io.BytesIO(body))

        _no_piece_of(KEY, _chat_failure(monkeypatch, config, answer))


def _long_key(length: int) -> str:
    return "".join("Ab+9/Cd=8_eF-7"[i % 14] for i in range(length))[:length]


@pytest.mark.parametrize("length", [1, 7, 8, 9, 500, 2000, 10000])
def test_a_key_of_any_length_echoed_into_a_cut_body_shows_none_of_it(
    monkeypatch: pytest.MonkeyPatch, length: int
) -> None:
    key = "sk" + _long_key(length - 2) if length > 2 else _long_key(length)
    config = LlmConfig("https://api.example.test/v1", "m", key)
    body = f"bad key {key} or {urllib.parse.quote(key, safe='')}; " * 3
    answer = urllib.error.HTTPError(
        config.chat_url, 401, "No", Message(), io.BytesIO(body.encode()[:4096])
    )

    shown = _chat_failure(monkeypatch, config, answer)

    assert "***" in shown, shown[:300]
    if length >= 8:
        _no_piece_of(key, shown)


@pytest.mark.parametrize(("kept", "shown"), [(7, True), (8, False), (9, False)])
def test_a_cut_hides_a_key_prefix_from_eight_characters_on(kept: int, shown: bool) -> None:
    key = "sk-INVENTED-0123456789"
    text = "bad key " + key[:kept]

    assert (key[:kept] in client.redact(key, text, cut=True)) is shown
    assert key[:kept] in client.redact(key, text)


@pytest.mark.parametrize(
    "cut_inside",
    [
        urllib.parse.quote(KEY, safe="")[:25],
        "".join(f"\\u{ord(c):04x}" for c in KEY)[:63],
        "".join(f"&#{ord(c)};" for c in KEY)[:47],
        "".join(f"&#x{ord(c):x};" for c in KEY)[:50],
    ],
)
def test_a_cut_inside_an_encoded_character_hides_the_key_before_it(cut_inside: str) -> None:
    assert client.redact(KEY, "bad key " + cut_inside, cut=True) == "bad key ***"


@pytest.mark.parametrize("status", [429, 503])
def test_a_long_key_still_lets_a_busy_server_be_asked_again(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    key = "sk" + _long_key(1998)
    config = LlmConfig("https://api.example.test/v1", "m", key)
    reply = json.dumps({"choices": [{"message": {"content": '{"ok": 1}'}}]}).encode()
    answers: list[Exception | bytes] = [
        urllib.error.HTTPError(
            config.chat_url, status, "Busy", Message(), io.BytesIO(f"busy {key}".encode())
        ),
        reply,
    ]

    def open_next(*_args: object, **_kwargs: object) -> object:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return contextlib.nullcontext(SimpleNamespace(read=lambda: answer))

    def opener(_config: LlmConfig) -> object:
        return SimpleNamespace(open=open_next)

    monkeypatch.setattr(client, "_opener", opener)
    value, attempt = ask(
        json_chat(config),
        [{"role": "user", "content": "hi"}],
        parse_json_reply,
        reprompt=str,
        label="test",
        sleep=lambda _s: None,
    )

    assert (value, attempt) == ({"ok": 1}, 2)


def test_a_key_in_the_base_url_is_taken_out_of_every_url_a_failure_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "sk-INVENTED-Ab12Cd34Ef56"
    config = LlmConfig(f"https://api.example.test/{key}/v1", "m", key)
    for answer in (
        urllib.error.HTTPError(config.chat_url, 500, "Error", Message(), io.BytesIO()),
        urllib.error.URLError(ConnectionRefusedError("refused")),
        urllib.error.URLError(TimeoutError("timed out")),
    ):
        shown = _chat_failure(monkeypatch, config, answer)

        assert "/***/v1" in shown and key not in shown, shown


@pytest.mark.parametrize("key", ["sk-INV\nENTED", "sk-INVENTED\r\n", "sk-INV ENTED", "sk-INV中文"])
def test_a_key_no_header_can_carry_is_refused_without_a_word_of_it(key: str) -> None:
    with pytest.raises(ValueError) as caught:
        LlmConfig("https://api.example.test/v1", "m", key)

    assert [n.code for n in notices_of(caught.value)] == ["llm.keyUnsendable"]
    assert "INV" not in _shown(caught.value)


def test_settings_save_a_pasted_key_without_the_spaces_around_it(rig: Rig) -> None:
    reply = rig.client.put(
        "/api/settings",
        json={
            "llm": {
                "source": "cloud",
                "cloud_url": "https://api.example.test/v1",
                "cloud_model": "m",
                "cloud_consent": True,
                "api_key": " sk-INVENTED-pasted\r\n",
            }
        },
    )

    assert reply.status_code == 200
    assert rig.secrets.get("llm_api_key") == "sk-INVENTED-pasted"


def test_the_connection_test_shows_no_spelling_of_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://api.example.test/v1/models"
    for echoed in SPELLINGS.values():
        moved = Message()
        moved["Location"] = f"https://api.example.test/?key={echoed}"

        def refuse(_url: str, _key: str | None, _moved: Message = moved) -> object:
            raise urllib.error.HTTPError(url, 302, "Found", _moved, io.BytesIO())

        monkeypatch.setattr(llm_check, "_get_json", refuse)
        found = llm_check._probe(LlmSource.CLOUD, url, KEY, "data", "id")  # pyright: ignore[reportPrivateUsage]

        assert echoed not in found.detail and "***" in found.detail


@pytest.mark.parametrize("route", ["/api/settings", "/api/llm/test"])
def test_a_key_no_header_can_carry_is_refused_when_saved_or_tested(rig: Rig, route: str) -> None:
    llm = {
        "source": "cloud",
        "cloud_url": "https://api.example.test/v1",
        "cloud_model": "m",
        "cloud_consent": True,
        "api_key": "sk-INVENTED inner-space",
    }
    send = rig.client.put if route == "/api/settings" else rig.client.post

    reply = send(route, json={"llm": llm})

    assert reply.status_code == 422
    assert [n["code"] for n in reply.json()["notices"]] == ["llm.keyUnsendable"]
    assert "INVENTED" not in reply.text
    assert rig.secrets.get("llm_api_key") is None
