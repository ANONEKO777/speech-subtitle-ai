"""No spelling of the API key reaches what the window, the log or a stored file can show. Every key
here is invented."""

from __future__ import annotations

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
