from __future__ import annotations

import http.client
import json
import threading
import urllib.error
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from backend.core import summarize, translate
from backend.core.model import Cue, FormatError
from backend.core.subtitle_io import parse_subs, render_subs, write_text_file
from backend.core.translate import (
    Batch,
    GlossaryEntry,
    Progress,
    ReplyError,
    TranslationError,
    Unit,
    build_request,
    parse_reply,
    plan_batches,
    resume_from,
    run,
    sentence_units,
)
from backend.llm import client
from backend.llm.ask import MAX_BACKOFF_S, MAX_RETRIES, json_chat
from backend.llm.client import LlmConfig, LlmError, Message


def make_cues(n: int, start_id: int = 1) -> list[Cue]:
    return [
        Cue(start_id + i, i * 2000, i * 2000 + 1500, f"Sentence number {start_id + i} is here.")
        for i in range(n)
    ]


def span(start: int, stop: int) -> Batch:
    return Batch(tuple(Unit(i, i + 1) for i in range(start, stop)))


def payload(messages: Sequence[Message]) -> dict[str, Any]:
    return json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "user"))


def target_ids(messages: Sequence[Message]) -> list[int]:
    return [cast("int", item["id"]) for item in payload(messages[:2])["translate"]]


def good_reply(messages: Sequence[Message], drop: int = 0) -> str:
    items = payload(messages[:2])["translate"][: len(payload(messages[:2])["translate"]) - drop]
    return json.dumps(
        {"translations": [{"id": item["id"], "zh": f"第{item['id']}句在這裡。"} for item in items]},
        ensure_ascii=False,
    )


class FakeLlm:
    def __init__(self, script: Callable[[int, Sequence[Message]], str | None] | None = None):
        self.script = script
        self.calls: list[list[Message]] = []

    def __call__(self, messages: Sequence[Message], temperature: float) -> str:
        self.calls.append(list(messages))
        reply = self.script(len(self.calls), messages) if self.script else None
        return good_reply(messages) if reply is None else reply

    def asked_ids(self) -> list[list[int]]:
        return [target_ids(call) for call in self.calls]


def no_sleep(_: float) -> None:
    return None


def run_all(
    cues: list[Cue],
    llm: FakeLlm,
    glossary: Sequence[GlossaryEntry] = (),
    *,
    batch_size: int = translate.BATCH_SIZE,
    max_retries: int = MAX_RETRIES,
    checkpoint: Callable[[list[Cue]], None] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
) -> list[Cue]:
    return translate.run(
        cues,
        llm,
        glossary,
        batch_size=batch_size,
        max_retries=max_retries,
        checkpoint=checkpoint,
        on_progress=on_progress,
        sleep=no_sleep,
    )


def test_translates_every_cue_and_leaves_timing_and_english_alone() -> None:
    cues = make_cues(70)
    result = run_all(cues, FakeLlm())
    assert len(result) == 70
    assert [(c.id, c.start_ms, c.end_ms, c.src) for c in result] == [
        (c.id, c.start_ms, c.end_ms, c.src) for c in cues
    ]
    assert all(c.zh == f"第{c.id}句在這裡。" for c in result)


def test_batches_carry_five_cues_of_context_as_plain_text_on_each_side() -> None:
    llm = FakeLlm()
    run_all(make_cues(70), llm, batch_size=30)
    assert llm.asked_ids() == [list(range(1, 31)), list(range(31, 61)), list(range(61, 71))]
    second = payload(llm.calls[1])
    assert second["context_before"] == " ".join(
        f"Sentence number {i} is here." for i in range(26, 31)
    )
    assert second["context_after"] == " ".join(
        f"Sentence number {i} is here." for i in range(61, 66)
    )
    assert payload(llm.calls[0])["context_before"] == ""
    assert payload(llm.calls[2])["context_after"] == ""
    assert list(payload(llm.calls[1])) == ["context_before", "context_after", "translate"]


def test_default_batch_is_ten_cues() -> None:
    llm = FakeLlm()
    run_all(make_cues(25), llm)
    assert [len(ids) for ids in llm.asked_ids()] == [10, 10, 5]


def test_multi_line_english_is_sent_on_one_line() -> None:
    cues = [Cue(1, 0, 1000, "first half\nsecond half")]
    llm = FakeLlm()
    run_all(cues, llm)
    assert payload(llm.calls[0])["translate"] == [{"id": 1, "en": "first half second half"}]


def test_short_reply_is_retried_and_the_retry_names_the_problem() -> None:
    llm = FakeLlm(lambda n, m: good_reply(m, drop=1) if n == 1 else None)
    result = run_all(make_cues(5), llm)
    assert all(c.zh for c in result)
    assert len(llm.calls) == 2
    feedback = llm.calls[1][-1]
    assert feedback["role"] == "user"
    assert "missing ids [5]" in feedback["content"]
    assert llm.calls[1][-2]["role"] == "assistant"


@pytest.mark.parametrize(
    "bad",
    [
        "I cannot help with that.",
        '{"translations": [{"id": 1, "zh": "第',
        '{"answer": []}',
        '[{"id": 1}]',
        '[{"id": "1", "zh": "一"}]',
        '[{"id": true, "zh": "一"}]',
        "[1, 2]",
    ],
)
def test_malformed_json_is_retried(bad: str) -> None:
    llm = FakeLlm(lambda n, m: bad if n == 1 else None)
    result = run_all(make_cues(1), llm)
    assert result[0].zh
    assert len(llm.calls) == 2


def test_extra_id_and_duplicate_id_are_retried() -> None:
    extra = json.dumps([{"id": 1, "zh": "一"}, {"id": 2, "zh": "二"}, {"id": 99, "zh": "多"}])
    dup = json.dumps([{"id": 1, "zh": "一"}, {"id": 1, "zh": "又一"}, {"id": 2, "zh": "二"}])
    llm = FakeLlm(lambda n, m: [extra, dup, None][n - 1])
    run_all(make_cues(2), llm)
    assert len(llm.calls) == 3
    assert "unexpected ids [99]" in llm.calls[1][-1]["content"]
    assert "duplicate ids [1]" in llm.calls[2][-1]["content"]


def test_context_ids_in_the_reply_count_as_extra() -> None:
    cues = make_cues(6)
    request = build_request(cues, span(0, 3))
    reply = json.dumps([{"id": i, "zh": f"第{i}句"} for i in range(1, 5)])
    with pytest.raises(ReplyError, match=r"unexpected ids \[4\]"):
        parse_reply(reply, request, cues)


def test_retries_are_limited_to_three_then_the_batch_is_split() -> None:
    sizes: list[int] = []

    def script(n: int, m: Sequence[Message]) -> str | None:
        ids = target_ids(m)
        sizes.append(len(ids))
        return good_reply(m, drop=1) if len(ids) > 4 else None

    llm = FakeLlm(script)
    result = run_all(make_cues(12), llm, batch_size=12)
    assert all(c.zh for c in result)
    assert sizes == [12] * 4 + ([6] * 4 + [3] * 2) * 2
    assert sorted(i for ids in llm.asked_ids() if len(ids) == 3 for i in ids) == list(range(1, 13))


def test_split_keeps_context_from_the_neighbouring_batch() -> None:
    llm = FakeLlm(lambda n, m: good_reply(m, drop=1) if len(target_ids(m)) > 3 else None)
    run_all(make_cues(6), llm, batch_size=6, max_retries=0)
    right_half = next(c for c in llm.calls if target_ids(c) == [4, 5, 6])
    assert payload(right_half)["context_before"] == " ".join(
        f"Sentence number {i} is here." for i in (1, 2, 3)
    )


def test_a_single_cue_that_never_validates_raises_and_keeps_earlier_batches() -> None:
    saved: list[list[Cue]] = []

    def script(n: int, m: Sequence[Message]) -> str | None:
        return "nope" if 40 in target_ids(m) else None

    llm = FakeLlm(script)
    with pytest.raises(TranslationError, match="cue 40 could not be translated"):
        run_all(make_cues(60), llm, checkpoint=saved.append)
    assert [c.id for c in saved[-1] if c.zh] == list(range(1, 40))
    assert len([c for c in saved[-1] if not c.zh]) == 21


def test_mainland_wording_is_replaced_and_never_makes_a_retry() -> None:
    said = "我們創建了源碼的元數據，搜索接口，再運營存儲服務。"
    taiwan = "我們建立了原始碼的中繼資料，搜尋介面，再營運儲存服務。"

    def script(n: int, m: Sequence[Message]) -> str | None:
        items = payload(m[:2])["translate"]
        return json.dumps(
            {"translations": [{"id": item["id"], "zh": said} for item in items]},
            ensure_ascii=False,
        )

    llm = FakeLlm(script)
    result = run_all(make_cues(3), llm)
    assert len(llm.calls) == 1
    assert [c.zh for c in result] == [taiwan] * 3


def test_non_retryable_llm_error_stops_at_once() -> None:
    def script(n: int, m: Sequence[Message]) -> str | None:
        raise LlmError("cannot reach the LLM server at http://x/v1: refused")

    llm = FakeLlm(script)
    with pytest.raises(LlmError, match="http://x/v1"):
        run_all(make_cues(3), llm)
    assert len(llm.calls) == 1


def test_retryable_llm_error_backs_off_then_succeeds() -> None:
    delays: list[float] = []

    def script(n: int, m: Sequence[Message]) -> str | None:
        if n <= 2:
            raise LlmError("HTTP 503", retryable=True)
        return None

    llm = FakeLlm(script)
    result = translate.run(make_cues(2), llm, sleep=delays.append)
    assert all(c.zh for c in result)
    assert delays == [1.0, 2.0]


def test_progress_reports_cues_done_after_each_batch() -> None:
    events: list[Progress] = []
    run_all(make_cues(45), FakeLlm(), batch_size=30, on_progress=events.append)
    assert [(e.done, e.total, e.batch_cues) for e in events] == [(30, 45, 30), (45, 45, 15)]
    assert all(e.attempts == 1 and e.batch_seconds >= 0 for e in events)


def test_glossary_goes_into_the_system_prompt() -> None:
    llm = FakeLlm()
    glossary = [GlossaryEntry("poteto"), GlossaryEntry("agent", "代理程式")]
    run_all(make_cues(1), llm, glossary)
    system = llm.calls[0][0]["content"]
    assert "Glossary" in system
    assert '"poteto" must stay in its original English spelling' in system
    assert '"agent" must be translated as "代理程式"' in system


def test_no_glossary_section_without_a_glossary() -> None:
    llm = FakeLlm()
    run_all(make_cues(1), llm)
    system = llm.calls[0][0]["content"]
    assert "Glossary" not in system
    assert "<<" not in system
    assert "Taiwan" in system


def test_glossary_entry_rejects_blank_and_multiline() -> None:
    for args in [("",), ("  ",), ("a\nb",), ("a", "b\nc")]:
        with pytest.raises(ValueError):
            GlossaryEntry(*args)


def test_plan_batches_chunks_each_untranslated_run() -> None:
    cues = make_cues(10)
    cues[3] = replace(cues[3], zh="好")
    cues[4] = replace(cues[4], zh="好")
    assert plan_batches(cues, 3) == [span(0, 3), span(5, 8), span(8, 10)]
    assert plan_batches([replace(c, zh="好") for c in cues]) == []
    assert plan_batches([]) == []
    with pytest.raises(ValueError):
        plan_batches(cues, 0)


def test_resume_asks_only_for_untranslated_cues() -> None:
    cues = make_cues(70)
    done = [replace(c, zh="舊") if c.id <= 30 else c for c in cues]
    llm = FakeLlm()
    result = run_all(done, llm, batch_size=30)
    assert llm.asked_ids() == [list(range(31, 61)), list(range(61, 71))]
    assert [c.zh for c in result[:30]] == ["舊"] * 30


def test_resume_from_drops_translations_whose_cue_changed() -> None:
    cues = make_cues(3)
    previous = [
        replace(cues[0], zh="一"),
        replace(cues[1], zh="二", src="Something else entirely."),
        replace(cues[2], zh="三", end_ms=cues[2].end_ms + 1),
    ]
    assert [c.zh for c in resume_from(cues, previous)] == ["一", "", ""]


def test_translate_file_resumes_after_a_crash_and_converges(tmp_path: Path) -> None:
    source, dest = tmp_path / "subs.en.json", tmp_path / "subs.zh-TW.json"
    write_text_file(source, render_subs(make_cues(70)))

    def die_on_third_batch(n: int, m: Sequence[Message]) -> str | None:
        if n == 3:
            raise LlmError("cannot reach the LLM server at http://127.0.0.1:1/v1: refused")
        return None

    with pytest.raises(LlmError):
        translate.translate_file(source, dest, FakeLlm(die_on_third_batch), batch_size=30)
    partial = parse_subs(dest.read_text(encoding="utf-8"))
    assert [c.id for c in partial if c.zh] == list(range(1, 61))

    llm = FakeLlm()
    result = translate.translate_file(source, dest, llm, batch_size=30)
    assert llm.asked_ids() == [list(range(61, 71))]
    uninterrupted = tmp_path / "other.json"
    translate.translate_file(source, uninterrupted, FakeLlm(), batch_size=30)
    assert dest.read_bytes() == uninterrupted.read_bytes()
    assert parse_subs(dest.read_text(encoding="utf-8")) == result

    again = FakeLlm()
    translate.translate_file(source, dest, again, batch_size=30)
    assert again.calls == []


def test_translate_file_refuses_a_corrupt_destination(tmp_path: Path) -> None:
    source, dest = tmp_path / "subs.en.json", tmp_path / "subs.zh-TW.json"
    write_text_file(source, render_subs(make_cues(2)))
    dest.write_text("{not json", encoding="utf-8")
    with pytest.raises(FormatError, match="cannot resume"):
        translate.translate_file(source, dest, FakeLlm())


def test_parse_reply_accepts_the_wrappers_models_add() -> None:
    cues = make_cues(2)
    request = build_request(cues, span(0, 2))
    body = '[{"id": 1, "zh": "第一句在這裡。"}, {"id": 2, "zh": "第二句在這裡。"}]'
    for text in [
        body,
        f"```json\n{body}\n```",
        f"<think>\nlet me think\n</think>\n\n{body}",
        '{"translations": ' + body + "}",
    ]:
        assert parse_reply(text, request, cues) == {1: "第一句在這裡。", 2: "第二句在這裡。"}


def test_parse_reply_cleans_line_breaks_and_padding() -> None:
    cues = make_cues(1)
    request = build_request(cues, span(0, 1))
    text = json.dumps([{"id": 1, "zh": "  第一行 \r\n\n  第二行  "}], ensure_ascii=False)
    assert parse_reply(text, request, cues) == {1: "第一行\n第二行"}


def test_parse_reply_swaps_unambiguous_mainland_terms_for_taiwan_ones() -> None:
    cues = [Cue(1, 0, 1000, "The video software code is fast, user.")]
    request = build_request(cues, span(0, 1))
    text = json.dumps([{"id": 1, "zh": "視頻軟件的代碼很快，用戶，性能"}], ensure_ascii=False)
    assert parse_reply(text, request, cues) == {1: "影片軟體的程式碼很快，使用者，效能"}


@pytest.mark.parametrize(
    ("zh", "message"),
    [
        ("", "empty translation"),
        ("  \n ", "empty translation"),
        ("这是简体字", "Simplified characters"),
        ("Sentence number 1 is here.", "not translated"),
    ],
)
def test_parse_reply_rejects_unusable_text(zh: str, message: str) -> None:
    cues = make_cues(1)
    request = build_request(cues, span(0, 1))
    with pytest.raises(ReplyError, match=message):
        parse_reply(json.dumps([{"id": 1, "zh": zh}]), request, cues)


def test_parse_reply_rejects_a_translation_far_longer_than_its_english() -> None:
    cues = [Cue(1, 0, 1000, "So, you know,")]
    request = build_request(cues, span(0, 1))
    zh = "所以你知道的我們接下來要談的是另一個完全不同的主題而且很長"
    with pytest.raises(ReplyError, match="far longer"):
        parse_reply(json.dumps([{"id": 1, "zh": zh}], ensure_ascii=False), request, cues)


def test_parse_reply_rejects_a_stub_for_a_long_cue() -> None:
    cues = [Cue(1, 0, 1000, "as an engineer and impart them into my team of agents so that I")]
    request = build_request(cues, span(0, 1))
    with pytest.raises(ReplyError, match="far shorter"):
        parse_reply('[{"id": 1, "zh": "了。"}]', request, cues)


def test_short_english_may_stay_untranslated() -> None:
    cues = [Cue(1, 0, 1000, "Cursor.")]
    request = build_request(cues, span(0, 1))
    assert parse_reply('[{"id": 1, "zh": "Cursor。"}]', request, cues) == {1: "Cursor。"}


def test_taiwan_prompt_names_the_register() -> None:
    system = build_request(make_cues(1), span(0, 1)).messages[0]["content"]
    for needle in ["Traditional Chinese", "Taiwan", "影片", "軟體", "Simplified"]:
        assert needle in system


def test_batch_rejects_empty_spans_and_splits_in_two() -> None:
    with pytest.raises(ValueError):
        Batch(())
    with pytest.raises(ValueError):
        Unit(3, 3)
    assert span(0, 5).halves() == (span(0, 2), span(2, 5))


class Server:
    def __init__(self, handler: Callable[[BaseHTTPRequestHandler, bytes], None]) -> None:
        self.requests: list[tuple[dict[str, str], dict[str, object]]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append(
                    ({k.lower(): v for k, v in self.headers.items()}, json.loads(body))
                )
                handler(self, body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"


@contextmanager
def serve(handler: Callable[[BaseHTTPRequestHandler, bytes], None]) -> Generator[Server]:
    server = Server(handler)
    thread = threading.Thread(target=server.httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.httpd.shutdown()
        server.httpd.server_close()
        thread.join()


def send(handler: BaseHTTPRequestHandler, status: int, body: object) -> None:
    data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def completion(text: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


USER: Message = {"role": "user", "content": "hi"}


def test_client_posts_an_openai_chat_request_and_returns_the_text() -> None:
    with serve(lambda h, b: send(h, 200, completion("你好"))) as server:
        config = LlmConfig(
            server.url, "m1", "sk-secret", extra_body={"chat_template_kwargs": {"x": 1}}
        )
        assert client.chat(config, [USER], temperature=0.25, json_mode=True) == "你好"
    headers, body = server.requests[0]
    assert headers["authorization"] == "Bearer sk-secret"
    assert body["model"] == "m1"
    assert body["messages"] == [USER]
    assert body["temperature"] == 0.25
    assert body["response_format"] == {"type": "json_object"}
    assert body["chat_template_kwargs"] == {"x": 1}
    assert body["stream"] is False


def test_client_sends_no_auth_header_without_a_key() -> None:
    with serve(lambda h, b: send(h, 200, completion("ok"))) as server:
        client.chat(LlmConfig(server.url, "m"), [USER])
    assert "authorization" not in server.requests[0][0]
    assert "response_format" not in server.requests[0][1]


def test_unreachable_server_error_names_the_base_url_and_not_the_key() -> None:
    with serve(lambda h, b: send(h, 200, completion("ok"))) as server:
        dead = server.url
    config = LlmConfig(dead, "m", "sk-secret")
    with pytest.raises(LlmError, match="cannot reach the LLM server at " + dead) as info:
        client.chat(config, [USER])
    assert not info.value.retryable
    assert "sk-secret" not in str(info.value)
    assert "sk-secret" not in repr(config)


def test_http_errors_say_if_asking_again_can_help() -> None:
    with serve(lambda h, b: send(h, 503, {"error": "loading model"})) as server:
        with pytest.raises(LlmError, match="HTTP 503") as info:
            client.chat(LlmConfig(server.url, "m"), [USER])
        assert info.value.retryable
    with serve(lambda h, b: send(h, 401, {"error": "bad key"})) as server:
        with pytest.raises(LlmError, match="HTTP 401.*bad key") as info:
            client.chat(LlmConfig(server.url, "m", "sk-secret"), [USER])
        assert not info.value.retryable
        assert "sk-secret" not in str(info.value)


@pytest.mark.parametrize(
    "body", [b"not json", b"[]", b'{"choices": []}', b'{"choices": [{"message": {}}]}']
)
def test_client_rejects_a_body_that_is_not_a_chat_completion(body: bytes) -> None:
    with serve(lambda h, b: send(h, 200, body)) as server:
        with pytest.raises(LlmError, match="did not return a chat completion"):
            client.chat(LlmConfig(server.url, "m"), [USER])


def test_client_does_not_follow_a_redirect_off_the_machine() -> None:
    def redirect(h: BaseHTTPRequestHandler, b: bytes) -> None:
        h.send_response(302)
        h.send_header("Location", "http://203.0.113.9/v1/chat/completions")
        h.send_header("Content-Length", "0")
        h.end_headers()

    with serve(redirect) as server:
        with pytest.raises(LlmError, match="redirected"):
            client.chat(LlmConfig(server.url, "m"), [USER])


def test_local_requests_ignore_proxy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    with serve(lambda h, b: send(h, 200, completion("direct"))) as server:
        assert client.chat(LlmConfig(server.url, "m"), [USER]) == "direct"


def test_config_knows_loopback_and_validates() -> None:
    assert LlmConfig("http://127.0.0.1:8080/v1", "m").is_local
    assert LlmConfig("http://localhost:11434/v1/", "m").is_local
    assert not LlmConfig("https://api.openai.com/v1", "m").is_local
    assert not LlmConfig("http://127.0.0.1.evil.example/v1", "m").is_local
    assert (
        LlmConfig("http://localhost:1/v1/", "m").chat_url
        == "http://localhost:1/v1/chat/completions"
    )
    for url in ["", "127.0.0.1:8080", "ftp://x/v1", "http:///v1"]:
        with pytest.raises(ValueError):
            LlmConfig(url, "m")
    with pytest.raises(ValueError):
        LlmConfig("http://127.0.0.1/v1", "")


def test_translating_through_a_real_http_server(tmp_path: Path) -> None:
    def answer(h: BaseHTTPRequestHandler, raw: bytes) -> None:
        messages = cast("list[Message]", json.loads(raw)["messages"])
        send(h, 200, completion(good_reply(messages)))

    source, dest = tmp_path / "subs.en.json", tmp_path / "subs.zh-TW.json"
    write_text_file(source, render_subs(make_cues(40)))
    with serve(answer) as server:
        config = LlmConfig(server.url, "m")

        def chat(messages: Sequence[Message], temperature: float) -> str:
            return client.chat(config, messages, temperature=temperature, json_mode=True)

        result = translate.translate_file(source, dest, chat, batch_size=30)
    assert len(server.requests) == 2
    assert all(body["response_format"] == {"type": "json_object"} for _, body in server.requests)
    assert len(result) == 40
    assert all(c.zh for c in parse_subs(dest.read_text(encoding="utf-8")))


def test_prompt_ships_with_the_package() -> None:
    from importlib.resources import files

    prompt = files("backend.core") / "prompts" / "translate.md"
    assert prompt.is_file()
    assert "<<GLOSSARY>>" in prompt.read_text(encoding="utf-8")


def fragments(*texts: str, start_id: int = 1) -> list[Cue]:
    return [Cue(start_id + i, i * 2000, i * 2000 + 1500, text) for i, text in enumerate(texts)]


TALK = fragments(
    "So last month, I did something pretty",
    "crazy. I shipped 2,000 PRs.",
    "A lot of how I'm able to do this is",
    "through trust, and I think a lot",
    "about trust.",
    "Right?",
)


def test_cues_are_grouped_into_sentences_and_packed_without_cutting_one() -> None:
    assert [(u.start, u.stop) for u in sentence_units(TALK, 0, 6, 6)] == [(0, 2), (2, 5), (5, 6)]
    assert [[(u.start, u.stop) for u in b.units] for b in plan_batches(TALK, 4)] == [
        [(0, 2)],
        [(2, 5), (5, 6)],
    ]
    assert [[(u.start, u.stop) for u in b.units] for b in plan_batches(TALK, 5)] == [
        [(0, 2), (2, 5)],
        [(5, 6)],
    ]


def test_speech_that_runs_on_without_a_sentence_end_is_cut_at_the_limit() -> None:
    cues = fragments(*[f"and then word{i}" for i in range(7)])
    assert [(u.start, u.stop) for u in sentence_units(cues, 0, 7, 3)] == [(0, 3), (3, 6), (6, 7)]


def test_the_request_marks_each_cue_of_a_sentence_and_nothing_else() -> None:
    request = build_request(TALK, plan_batches(TALK, 5)[0])
    assert request.units == ((1, 2), (3, 4, 5))
    assert request.ids == (1, 3)
    entries = payload(request.messages)["translate"]
    assert entries == [
        {
            "id": 1,
            "en": "[[1]]So last month, I did something pretty [[2]]crazy. I shipped 2,000 PRs.",
        },
        {
            "id": 3,
            "en": "[[3]]A lot of how I'm able to do this is [[4]]through trust, and I think a lot "
            "[[5]]about trust.",
        },
    ]
    assert payload(build_request(TALK, plan_batches(TALK, 5)[1]).messages)["translate"] == [
        {"id": 6, "en": "Right?"}
    ]


def test_a_sentence_reply_is_split_back_into_cues_at_the_markers() -> None:
    request = build_request(TALK, plan_batches(TALK, 5)[0])
    reply = json.dumps(
        {
            "translations": [
                {
                    "id": 1,
                    "zh": "[[1]]所以上個月，我做了一件相當 [[2]]瘋狂的事。我送出 2,000 個 PR。",
                },
                {
                    "id": 3,
                    "zh": "[[3]]我能做到這件事，很大程度上[[4]]是因為信任，我常常[[5]]思考。",
                },
            ]
        },
        ensure_ascii=False,
    )
    assert parse_reply(reply, request, TALK) == {
        1: "所以上個月，我做了一件相當",
        2: "瘋狂的事。我送出 2,000 個 PR。",
        3: "我能做到這件事，很大程度上",
        4: "是因為信任，我常常",
        5: "思考。",
    }


@pytest.mark.parametrize(
    ("zh", "message"),
    [
        ("[[3]]我能做到這件事，[[5]]思考信任。", "contains \\[\\[3\\]\\] \\[\\[5\\]\\]"),
        ("[[4]]是因為信任，[[3]]我能做到，[[5]]思考信任。", "once each, in that order"),
        ("我能做到這件事，[[3]]很大[[4]]是因為信任，[[5]]思考信任。", "text before"),
        ("我能做到這件事，是因為信任，思考信任。", "but contains none"),
        ("[[3]]我能做到這件事，[[4]][[5]]思考信任。", "cue 4 has an empty translation"),
    ],
)
def test_a_sentence_reply_with_wrong_markers_is_rejected(zh: str, message: str) -> None:
    request = build_request(TALK, plan_batches(TALK, 5)[0])
    reply = json.dumps(
        {
            "translations": [
                {"id": 1, "zh": "[[1]]所以上個月，我做了一件相當[[2]]瘋狂的事。"},
                {"id": 3, "zh": zh},
            ]
        },
        ensure_ascii=False,
    )
    with pytest.raises(ReplyError, match=message):
        parse_reply(reply, request, TALK)


def test_a_sentence_that_never_validates_is_split_inside_the_sentence() -> None:
    cues = fragments(
        "A lot of how I'm able to do this is",
        "through trust, and I think a lot",
        "about trust.",
    )
    asked: list[list[str]] = []

    def script(call: int, messages: Sequence[Message]) -> str | None:
        entries = payload(messages[:2])["translate"]
        asked.append([item["en"] for item in entries])
        if any("[[" in item["en"] for item in entries):
            replies = [{"id": item["id"], "zh": "沒有標記。"} for item in entries]
            return json.dumps({"translations": replies})
        return None

    llm = FakeLlm(script)
    out = run(cues, llm, max_retries=1, sleep=no_sleep)
    assert [c.zh for c in out] == ["第1句在這裡。", "第2句在這裡。", "第3句在這裡。"]
    assert asked[0] == [
        "[[1]]A lot of how I'm able to do this is [[2]]through trust, and I think a lot "
        "[[3]]about trust."
    ]
    assert ["A lot of how I'm able to do this is"] in asked


def test_a_server_that_keeps_failing_is_reported_not_split() -> None:
    cues = make_cues(10)
    calls: list[int] = []
    waits: list[float] = []

    def chat(messages: Sequence[Message], temperature: float) -> str:
        calls.append(len(messages))
        raise LlmError("http://llm.test/v1/chat/completions answered HTTP 503", retryable=True)

    with pytest.raises(LlmError, match="llm.test.*HTTP 503"):
        run(cues, chat, sleep=waits.append)
    assert len(calls) == MAX_RETRIES + 1


def test_retry_after_from_the_server_sets_the_wait() -> None:
    waits: list[float] = []

    def chat(messages: Sequence[Message], temperature: float) -> str:
        if len(waits) < 2:
            raise LlmError("busy", retryable=True, retry_after_s=20.0 if not waits else 9999.0)
        return good_reply(messages)

    run(make_cues(2), chat, sleep=waits.append)
    assert waits == [20.0, MAX_BACKOFF_S]


def test_glossary_terms_with_quotes_stay_inside_their_quotes() -> None:
    system = build_request(
        make_cues(1),
        span(0, 1),
        [GlossaryEntry('say "hi"', 'C:\\x"y'), GlossaryEntry("Cursor")],
    ).messages[0]["content"]
    assert '- "say \\"hi\\"" must be translated as "C:\\\\x\\"y"' in system
    assert '- "Cursor" must stay in its original English spelling' in system


def test_json_chat_asks_for_a_json_object() -> None:
    with serve(lambda h, b: send(h, 200, completion('{"translations": []}'))) as server:
        chat = json_chat(LlmConfig(server.url, "m"))
        assert chat([USER], 0.3) == '{"translations": []}'
    body = server.requests[0][1]
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.3


def test_summary_chat_caps_the_reply_length() -> None:
    with serve(lambda h, b: send(h, 200, completion("{}"))) as server:
        summarize.summary_chat(LlmConfig(server.url, "m"))([USER], 0.0)
        json_chat(LlmConfig(server.url, "m"))([USER], 0.0)
    assert server.requests[0][1]["max_tokens"] == summarize.REPLY_MAX_TOKENS
    assert "max_tokens" not in server.requests[1][1]


def test_a_key_echoed_by_the_server_is_redacted_from_the_error() -> None:
    def echo(h: BaseHTTPRequestHandler, b: bytes) -> None:
        send(h, 401, {"error": f"bad header {h.headers['Authorization']}"})

    with serve(echo) as server:
        with pytest.raises(LlmError, match="Bearer \\*\\*\\*") as info:
            client.chat(LlmConfig(server.url, "m", "sk-secret"), [USER])
    assert "sk-secret" not in str(info.value)


def test_a_key_straddling_the_error_body_cut_is_redacted_before_truncating() -> None:
    key = "sk-secret-0123456789"

    def echo(h: BaseHTTPRequestHandler, b: bytes) -> None:
        send(h, 401, {"error": "x" * 480 + key + " tail"})

    with serve(echo) as server:
        with pytest.raises(LlmError) as info:
            client.chat(LlmConfig(server.url, "m", key), [USER])
    assert "sk-secret" not in str(info.value)
    assert "x" * 400 in str(info.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pw@127.0.0.1:1/v1",
        "http://user@127.0.0.1:1/v1",
        "http://127.0.0.1:1/v1?key=sk-secret",
        "http://127.0.0.1:1/v1#frag",
    ],
)
def test_base_url_cannot_carry_credentials_or_a_query(url: str) -> None:
    with pytest.raises(ValueError, match="user name, password, query or fragment") as info:
        LlmConfig(url, "m")
    assert "sk-secret" not in str(info.value)
    assert "pw" not in str(info.value)


def test_an_api_key_is_not_sent_over_plain_http_off_the_machine() -> None:
    with pytest.raises(ValueError, match="plain http to llm.example"):
        LlmConfig("http://llm.example/v1", "m", "sk-secret")
    LlmConfig("https://llm.example/v1", "m", "sk-secret")
    LlmConfig("http://llm.example/v1", "m")
    LlmConfig("http://127.0.0.1:8080/v1", "m", "sk-local")


class _Raises:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def open(self, *args: object, **kwargs: object) -> object:
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "retryable"),
    [
        (urllib.error.URLError(TimeoutError("timed out")), True),
        (TimeoutError("read timed out"), True),
        (ConnectionResetError(), True),
        (urllib.error.URLError(ConnectionResetError()), True),
        (http.client.RemoteDisconnected("closed"), True),
        (http.client.IncompleteRead(b"par", 10), True),
        (ConnectionRefusedError(), False),
        (urllib.error.URLError(ConnectionRefusedError()), False),
        (urllib.error.URLError("name not known"), False),
    ],
)
def test_transport_failures_are_llm_errors_and_only_transient_ones_are_retryable(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException, retryable: bool
) -> None:
    def opener(config: LlmConfig) -> _Raises:
        return _Raises(exc)

    monkeypatch.setattr(client, "_opener", opener)
    with pytest.raises(LlmError, match="http://127.0.0.1:1/v1") as info:
        client.chat(LlmConfig("http://127.0.0.1:1/v1", "m"), [USER])
    assert info.value.retryable is retryable


def test_a_body_cut_short_by_the_server_is_a_retryable_llm_error() -> None:
    def cut(h: BaseHTTPRequestHandler, b: bytes) -> None:
        h.send_response(200)
        h.send_header("Content-Length", "500")
        h.end_headers()
        h.wfile.write(b"{")
        h.close_connection = True

    with serve(cut) as server:
        with pytest.raises(LlmError) as info:
            client.chat(LlmConfig(server.url, "m"), [USER])
    assert info.value.retryable


def test_retry_after_seconds_are_read_from_the_header() -> None:
    def busy(h: BaseHTTPRequestHandler, b: bytes) -> None:
        h.send_response(429)
        h.send_header("Retry-After", "7")
        h.send_header("Content-Length", "0")
        h.end_headers()

    with serve(busy) as server:
        with pytest.raises(LlmError, match="HTTP 429") as info:
            client.chat(LlmConfig(server.url, "m"), [USER])
    assert info.value.retryable
    assert info.value.retry_after_s == 7.0


def test_default_glossary_keeps_product_names_in_english() -> None:
    from backend.core.translate import DEFAULT_GLOSSARY, glossary_block

    terms = {entry.term for entry in DEFAULT_GLOSSARY}
    assert {"Cursor", "Claude Code", "Copilot"} <= terms
    assert all(not entry.zh for entry in DEFAULT_GLOSSARY)
    assert '"Claude Code" must stay in its original English spelling' in glossary_block(
        DEFAULT_GLOSSARY
    )


def test_prompt_tells_the_model_to_drop_fillers_and_not_ask_do_you_know() -> None:
    system = build_request(make_cues(1), span(0, 1)).messages[0]["content"]
    assert "你知不知道" in system
    assert '"uh", "um"' in system


def test_parse_reply_drops_latin_fillers_left_by_the_model() -> None:
    cues = [Cue(1, 0, 1000, "uh, we shipped it, you know,")]
    request = build_request(cues, span(0, 1))
    reply = json.dumps([{"id": 1, "zh": "uh，我們出貨了，你知不知道，"}], ensure_ascii=False)
    assert parse_reply(reply, request, cues) == {1: "我們出貨了，"}


def untranslatable_third(_: int, messages: Sequence[Message]) -> str | None:
    items = payload(messages[:2])["translate"]
    if any(item["id"] == 3 for item in items):
        reply = [
            {"id": i["id"], "zh": i["en"] if i["id"] == 3 else f"第{i['id']}句在這裡。"}
            for i in items
        ]
        return json.dumps({"translations": reply}, ensure_ascii=False)
    return None


def test_a_cue_that_cannot_be_translated_stops_the_run_by_default() -> None:
    with pytest.raises(TranslationError, match="cue 3"):
        run_all(make_cues(5), FakeLlm(untranslatable_third), batch_size=5)


def test_keep_english_lets_one_stubborn_cue_through_and_translates_the_rest() -> None:
    cues = make_cues(5)
    result = translate.run(
        cues,
        FakeLlm(untranslatable_third),
        batch_size=5,
        sleep=no_sleep,
        keep_english=True,
    )
    assert result[2].zh == cues[2].src
    assert [c.zh for c in result if c.id != 3] == [f"第{i}句在這裡。" for i in (1, 2, 4, 5)]


KEEP_CURSOR = (GlossaryEntry("Cursor"),)


@pytest.mark.parametrize("zh", ["我們使用 Cursor。", "我們用 cursor 工具。"])
def test_a_kept_glossary_term_in_the_english_must_be_in_the_chinese(zh: str) -> None:
    cues = [Cue(1, 0, 1000, "We learned from cursor's agent window.")]
    request = build_request(cues, span(0, 1))
    reply = json.dumps([{"id": 1, "zh": zh}], ensure_ascii=False)
    assert parse_reply(reply, request, cues, KEEP_CURSOR) == {1: zh}


def test_a_dropped_or_translated_kept_term_is_rejected_with_the_reason() -> None:
    cues = [Cue(1, 0, 1000, "We learned from cursor's agent window.")]
    request = build_request(cues, span(0, 1))
    reply = json.dumps([{"id": 1, "zh": "我們從游標的代理視窗學到。"}], ensure_ascii=False)
    with pytest.raises(ReplyError, match="must keep .Cursor."):
        parse_reply(reply, request, cues, KEEP_CURSOR)


def test_a_kept_term_is_not_required_inside_another_word() -> None:
    cues = [Cue(1, 0, 1000, "Pick the cursors you like, okay?")]
    request = build_request(cues, span(0, 1))
    reply = json.dumps([{"id": 1, "zh": "挑你喜歡的游標，好嗎？"}], ensure_ascii=False)
    assert parse_reply(reply, request, cues, KEEP_CURSOR)[1] == "挑你喜歡的游標，好嗎？"


def test_the_run_reprompts_when_the_model_drops_a_kept_term() -> None:
    cues = [Cue(1, 0, 1000, "We learned from Cursor's agent window.")]
    replies = ["我們從游標的代理視窗學到。", "我們從 Cursor 的代理視窗學到。"]

    def script(call: int, _messages: Sequence[Message]) -> str:
        return json.dumps(
            {"translations": [{"id": 1, "zh": replies[call - 1]}]}, ensure_ascii=False
        )

    llm = FakeLlm(script)
    out = run_all(cues, llm, KEEP_CURSOR)
    assert out[0].zh == replies[1]
    assert "must keep" in str(llm.calls[1][-1])
