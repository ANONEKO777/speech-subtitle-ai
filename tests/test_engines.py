import json
import subprocess
import sys
import threading
import time
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from backend.core.audio import SAMPLE_RATE
from backend.core.model import Segment, Word
from backend.core.segmenter import to_cues
from backend.core.vad import Chunk
from backend.engines import cli
from backend.engines.base import (
    EngineCancelled,
    EngineError,
    EngineFailedError,
    EngineOutputError,
    EngineTimeoutError,
    EngineUnavailableError,
    ProgressCb,
    segment_of,
)
from backend.engines.chunks import (
    capitalize_pronoun_i,
    repair_boundaries,
    transcribe_chunks,
    trim_overlaps,
)
from backend.engines.crispasr import CrispAsrEngine
from backend.engines.table import ENGINES, create_engine, engine_paths, spec_for, spec_for_model
from backend.engines.whispercpp import WhisperCppEngine
from backend.manager import registry
from backend.manager.profiles import Device
from backend.manager.storage import Storage, StorageConfig

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = FIXTURES / "engines"
FAKE_CLI = RECORDED / "fake_cli.py"
WAV_15S = FIXTURES / "en_15s.wav"


def touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


class FakeWhisper(WhisperCppEngine):
    def __init__(self, tmp_path: Path, *fake_args: str) -> None:
        super().__init__(touch(tmp_path / "whisper-cli.exe"), touch(tmp_path / "model.bin"))
        self.fake_args = fake_args
        self.inputs: list[Path] = []

    def command(
        self, inputs: Sequence[Path], output_bases: Sequence[Path], language: str
    ) -> list[str]:
        self.inputs = list(inputs)
        return [sys.executable, str(FAKE_CLI), *self.fake_args, *map(str, output_bases)]


class FakeCrisp(CrispAsrEngine):
    def __init__(self, tmp_path: Path, *fake_args: str) -> None:
        super().__init__(
            touch(tmp_path / "crispasr.exe"),
            touch(tmp_path / "qwen3.gguf"),
            touch(tmp_path / "aligner.gguf"),
        )
        self.fake_args = fake_args
        self.inputs: list[Path] = []

    def command(
        self, inputs: Sequence[Path], output_bases: Sequence[Path], language: str
    ) -> list[str]:
        self.inputs = list(inputs)
        return [sys.executable, str(FAKE_CLI), *self.fake_args, *map(str, output_bases)]


def whisper_json(*segments: dict[str, object]) -> str:
    return json.dumps({"transcription": list(segments)})


def tok(text: str, start: int = 0, end: int = 0) -> dict[str, object]:
    return {"text": text, "offsets": {"from": start, "to": end}}


def seg(start: int, end: int, *tokens: dict[str, object]) -> dict[str, object]:
    return {"offsets": {"from": start, "to": end}, "text": "", "tokens": list(tokens)}


def recorded(name: str) -> str:
    return str(RECORDED / name)


def run_whisper(tmp_path: Path, payload: str | bytes) -> list[Segment]:
    out = tmp_path / "out.json"
    if isinstance(payload, bytes):
        out.write_bytes(payload)
    else:
        out.write_text(payload, encoding="utf-8")
    engine = FakeWhisper(tmp_path, "--json", str(out))
    return engine.transcribe(WAV_15S)


def test_whisper_words_come_from_the_recorded_tokens(tmp_path: Path) -> None:
    engine = FakeWhisper(tmp_path, "--json", recorded("whisper_15s.json"))
    (segment,) = engine.transcribe(WAV_15S)
    assert engine.supports_word_timestamps
    assert segment.text == "For more information or to volunteer, please visit LibriVox.org."
    words = segment.words
    assert words is not None
    assert [w.text for w in words][:3] == ["For", "more", "information"]
    assert words[-1].text == "LibriVox.org."
    assert all(w.end_ms >= w.start_ms for w in words)
    assert [w.start_ms for w in words] == sorted(w.start_ms for w in words)
    assert (segment.start_ms, segment.end_ms) == (0, 7160)


def test_whisper_drops_special_tokens_and_annotations(tmp_path: Path) -> None:
    payload = whisper_json(
        seg(
            0,
            1000,
            tok("[_BEG_]"),
            tok(" [", 0, 10),
            tok("BL"),
            tok("ANK"),
            tok("_AUDIO"),
            tok("]", 900, 1000),
        ),
        seg(
            1000,
            3000,
            tok("[_BEG_]"),
            tok(" Hello", 1000, 1400),
            tok(" [", 1400, 1500),
            tok("Music", 1500, 1600),
            tok("]", 1600, 1700),
            tok(" there", 1700, 2000),
            tok("[_TT_300]", 2000, 2000),
        ),
        seg(3000, 4000, tok(" [", 3000, 3100), tok(" Silence", 3100, 3500), tok(" ]", 3500, 4000)),
    )
    segments = run_whisper(tmp_path, payload)
    assert [s.text for s in segments] == ["Hello there"]
    assert [(w.text, w.start_ms, w.end_ms) for w in segments[0].words or ()] == [
        ("Hello", 1000, 1400),
        ("there", 1700, 2000),
    ]


def test_whisper_joins_split_tokens_into_one_word(tmp_path: Path) -> None:
    payload = whisper_json(
        seg(
            0,
            900,
            tok(" im", 0, 200),
            tok("port", 200, 500),
            tok("ant", 500, 700),
            tok(",", 700, 760),
            tok(" yes", 800, 900),
            tok("\n", 900, 900),
        )
    )
    (segment,) = run_whisper(tmp_path, payload)
    assert [w.text for w in segment.words or ()] == ["important,", "yes"]


def test_invalid_utf8_in_engine_output_is_an_error_not_a_guess(tmp_path: Path) -> None:
    with pytest.raises(EngineOutputError, match="not valid UTF-8"):
        run_whisper(tmp_path, b'{"transcription": [{"text": "\xff"}]}')


def test_unexpected_json_shape_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EngineOutputError, match="unexpected whisper.cpp JSON"):
        run_whisper(tmp_path, json.dumps({"transcription": [{"offsets": {}}]}))


def test_crispasr_uses_aligned_words_from_the_recorded_output(tmp_path: Path) -> None:
    engine = FakeCrisp(tmp_path, "--json", recorded("crispasr_15s.json"))
    (segment,) = engine.transcribe(WAV_15S)
    words = segment.words
    assert words is not None
    assert [w.text for w in words][:4] == ["Box", "recordings", "are", "in"]
    assert (words[0].start_ms, words[0].end_ms) == (0, 240)
    assert segment.text.startswith("Box recordings are in the public domain.")


def test_crispasr_segment_without_words_is_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"transcription": [{"offsets": {"from": 0, "to": 5}, "text": "hi"}]}),
        encoding="utf-8",
    )
    with pytest.raises(EngineOutputError, match="unexpected CrispASR JSON"):
        FakeCrisp(tmp_path, "--json", str(bad)).transcribe(WAV_15S)


@pytest.mark.parametrize(
    ("make", "stderr"),
    [(FakeWhisper, "whisper_stderr.txt"), (FakeCrisp, "crispasr_stderr.txt")],
)
def test_progress_rises_from_zero_to_one_across_inputs(
    tmp_path: Path, make: type[FakeWhisper] | type[FakeCrisp], stderr: str
) -> None:
    payload = "whisper_15s.json" if make is FakeWhisper else "crispasr_15s.json"
    engine = make(tmp_path, "--json", recorded(payload), "--stderr", recorded(stderr))
    seen: list[float] = []
    results = engine.transcribe_many([WAV_15S, WAV_15S], progress_cb=seen.append)
    assert len(results) == 2
    assert seen[0] == 0.0
    assert seen[-1] == 1.0
    assert seen == sorted(set(seen))
    assert 0.5 in seen


def test_progress_follows_percent_lines_within_one_file(tmp_path: Path) -> None:
    lines = ["main: processing 'a.wav' (1 samples)"]
    lines += [f"whisper_print_progress_callback: progress = {p}%" for p in (5, 5, 40, 30, 100)]
    stderr = tmp_path / "stderr.txt"
    stderr.write_text("\n".join(lines), encoding="utf-8")
    engine = FakeWhisper(tmp_path, "--json", recorded("whisper_15s.json"), "--stderr", str(stderr))
    seen: list[float] = []
    engine.transcribe(WAV_15S, progress_cb=seen.append)
    assert seen == pytest.approx([0.0, 0.05, 0.4, 1.0])


def test_nonzero_exit_reports_the_code_and_the_last_stderr_lines(tmp_path: Path) -> None:
    stderr = tmp_path / "stderr.txt"
    stderr.write_text("loading\nfatal: model is corrupt\n", encoding="utf-8")
    engine = FakeWhisper(tmp_path, "--exit", "3", "--stderr", str(stderr))
    with pytest.raises(EngineFailedError, match=r"code 3.*model is corrupt"):
        engine.transcribe(WAV_15S)


def child_is_alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return f'"{pid}"' in out


def test_cancel_stops_the_child_within_two_seconds(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid.txt"
    engine = FakeWhisper(tmp_path, "--hang", "60", "--pidfile", str(pidfile))
    cancel = threading.Event()
    raised: list[tuple[float, BaseException]] = []

    def work() -> None:
        try:
            engine.transcribe(WAV_15S, cancel=cancel)
        except EngineError as exc:
            raised.append((time.monotonic(), exc))

    thread = threading.Thread(target=work)
    thread.start()
    deadline = time.monotonic() + 10
    while not (pidfile.exists() and pidfile.read_text()) and time.monotonic() < deadline:
        time.sleep(0.05)
    pid = int(pidfile.read_text())
    asked = time.monotonic()
    cancel.set()
    thread.join(timeout=5)
    assert raised
    assert isinstance(raised[0][1], EngineCancelled)
    assert raised[0][0] - asked < 2
    time.sleep(0.2)
    assert not child_is_alive(pid)


def test_a_child_that_will_not_die_does_not_hide_why_the_run_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_wait = subprocess.Popen[bytes].wait

    def slow_wait(self: subprocess.Popen[bytes], timeout: float | None = None) -> int:
        real_wait(self, timeout=timeout)
        raise subprocess.TimeoutExpired("engine", timeout or 0)

    monkeypatch.setattr(subprocess.Popen, "wait", slow_wait)
    cancel = threading.Event()
    cancel.set()
    engine = FakeWhisper(tmp_path, "--hang", "60")
    with pytest.raises(EngineCancelled):
        engine.transcribe(WAV_15S, cancel=cancel)


def test_timeout_kills_the_child_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pidfile = tmp_path / "pid.txt"
    real_popen = subprocess.Popen

    def popen_a_started_child(command: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        # The engine's clock starts after Popen returns. Waiting here keeps the fake child's
        # interpreter startup out of the 0.5 s, so the pid file is there when the kill comes.
        proc = real_popen(command, **kwargs)
        give_up = time.monotonic() + 30
        while not (pidfile.is_file() and pidfile.read_text()) and time.monotonic() < give_up:
            time.sleep(0.01)
        return proc

    monkeypatch.setattr(subprocess, "Popen", popen_a_started_child)
    engine = FakeWhisper(tmp_path, "--hang", "60", "--pidfile", str(pidfile))
    engine.timeout_s = 0.5
    with pytest.raises(EngineTimeoutError, match="0.5 s"):
        engine.transcribe(WAV_15S)
    time.sleep(0.2)
    assert not child_is_alive(int(pidfile.read_text()))


def test_missing_binary_is_unavailable_and_transcribe_names_it(tmp_path: Path) -> None:
    missing = tmp_path / "no-such" / "whisper-cli.exe"
    engine = WhisperCppEngine(missing, touch(tmp_path / "m.bin"))
    assert engine.is_available() is False
    with pytest.raises(EngineUnavailableError, match="binary not found") as info:
        engine.transcribe(WAV_15S)
    assert str(missing) in str(info.value)


def test_missing_model_error_names_the_path(tmp_path: Path) -> None:
    model = tmp_path / "gone" / "ggml-large-v3-turbo.bin"
    engine = WhisperCppEngine(touch(tmp_path / "whisper-cli.exe"), model)
    assert not engine.is_available()
    with pytest.raises(EngineUnavailableError) as info:
        engine.transcribe(WAV_15S)
    assert str(model) in str(info.value)


def test_a_binary_that_cannot_start_is_reported_as_unavailable(tmp_path: Path) -> None:
    broken = tmp_path / "whisper-cli.exe"
    broken.write_bytes(b"not an executable")
    engine = WhisperCppEngine(broken, touch(tmp_path / "m.bin"))
    assert engine.is_available()
    with pytest.raises(EngineUnavailableError, match="cannot start"):
        engine.transcribe(WAV_15S)


def test_crispasr_needs_ascii_model_and_binary_paths(tmp_path: Path) -> None:
    folder = tmp_path / "模型"
    folder.mkdir()
    engine = CrispAsrEngine(
        touch(tmp_path / "crispasr.exe"), touch(folder / "qwen3.gguf"), touch(tmp_path / "a.gguf")
    )
    assert not engine.is_available()
    with pytest.raises(EngineUnavailableError, match="non-ASCII"):
        engine.transcribe(WAV_15S)


def test_crispasr_gets_an_ascii_copy_of_a_chinese_named_wav(tmp_path: Path) -> None:
    wav = tmp_path / "演講 第1集.wav"
    wav.write_bytes(WAV_15S.read_bytes())
    engine = FakeCrisp(tmp_path, "--json", recorded("crispasr_15s.json"))
    engine.transcribe(wav)
    assert [str(p).isascii() for p in engine.inputs] == [True]
    assert engine.inputs[0] != wav


def test_whisper_reads_a_chinese_named_wav_where_it_is(tmp_path: Path) -> None:
    wav = tmp_path / "演講.wav"
    wav.write_bytes(WAV_15S.read_bytes())
    engine = FakeWhisper(tmp_path, "--json", recorded("whisper_15s.json"))
    engine.transcribe(wav)
    assert engine.inputs == [wav]


def test_whisper_command_line(tmp_path: Path) -> None:
    gpu = WhisperCppEngine(Path("w.exe"), Path("m.bin"), device=Device.CUDA)
    cpu = WhisperCppEngine(Path("w.exe"), Path("m.bin"), device=Device.CPU)
    ins, outs = [Path("a.wav"), Path("b.wav")], [Path("o0"), Path("o1")]
    command = gpu.command(ins, outs, "en")
    assert "-ng" not in command
    assert command[command.index("-l") + 1] == "en"
    assert [command[i + 1] for i, a in enumerate(command) if a == "-f"] == ["a.wav", "b.wav"]
    assert [command[i + 1] for i, a in enumerate(command) if a == "-of"] == ["o0", "o1"]
    assert "-ng" in cpu.command(ins, outs, "en")


def test_crispasr_command_line_keeps_its_own_vad_off(tmp_path: Path) -> None:
    engine = CrispAsrEngine(Path("c.exe"), Path("m.gguf"), Path("a.gguf"), device=Device.CPU)
    command = engine.command([Path("a.wav")], [Path("o0")], "en")
    assert "--vad" not in command
    assert command[command.index("-am") + 1] == "a.gguf"
    assert "--strict-pipeline" in command
    assert command[command.index("--gpu-backend") + 1] == "cpu"


def test_many_inputs_are_split_into_command_lines_that_fit() -> None:
    inputs = [
        Path(f"C:/Users/someone/AppData/Local/Temp/vst-asr-x/c{i:05d}.wav") for i in range(900)
    ]
    batches = list(WhisperCppEngine.command_batches(inputs, Path("C:/Temp/x")))
    assert len(batches) > 1
    assert batches[0][0] == 0
    assert all(a[1] == b[0] for a, b in zip(batches, batches[1:], strict=False))
    assert batches[-1][1] == 900


def test_engine_table_agrees_with_the_registry() -> None:
    reg = registry.load()
    for engine_id, spec in ENGINES.items():
        assert spec.id == engine_id
        assert reg.models[spec.model_id].engine == reg.runtimes[spec.runtime_id].engine
    assert spec_for_model("whisper-large-v3-turbo").id == "whispercpp-large-v3-turbo"
    assert spec_for_model("qwen3-asr-1.7b-q8_0").id == "crispasr-qwen3-asr-1.7b"
    crisp = create_engine("crispasr-qwen3-asr-1.7b", Path("c.exe"), Path("m"), aligner=Path("a"))
    assert reg.runtimes[spec_for(crisp.id).runtime_id].ascii_paths_only is crisp.ascii_paths_only
    assert reg.runtimes[spec_for("whispercpp-large-v3-turbo").runtime_id].ascii_paths_only is False


def test_engine_table_rejects_unknown_ids_and_a_missing_aligner() -> None:
    with pytest.raises(ValueError, match="unknown ASR engine 'nope'.*whispercpp"):
        spec_for("nope")
    with pytest.raises(ValueError, match="needs an aligner"):
        create_engine("crispasr-qwen3-asr-1.7b", Path("c.exe"), Path("m"))
    with pytest.raises(ValueError, match="no ASR engine runs model"):
        spec_for_model("qwen3-8b-q4_k_m")


def test_engine_paths_follow_the_downloader_layout(tmp_path: Path) -> None:
    reg = registry.load()
    storage = Storage(tmp_path / "data")
    whisper = engine_paths("whispercpp-large-v3-turbo", storage)
    assert (
        whisper.binary
        == tmp_path
        / "data"
        / "runtimes"
        / "whispercpp-b5454-win-cuda12.4"
        / "Release"
        / "whisper-cli.exe"
    )
    assert whisper.model == storage.model_file(reg.models["whisper-large-v3-turbo"])
    assert whisper.aligner is None
    cpu = engine_paths("whispercpp-large-v3-turbo", storage, runtime_id="whispercpp-b5454-win-cpu")
    assert cpu.binary.parent.parent.name == "whispercpp-b5454-win-cpu"
    assert cpu.model == whisper.model
    crisp = engine_paths("crispasr-qwen3-asr-1.7b", storage)
    assert crisp.aligner == storage.model_file(reg.models["qwen3-forced-aligner-0.6b-q8_0"])
    assert crisp.model == storage.model_file(reg.models["qwen3-asr-1.7b-q8_0"])


def test_engine_paths_use_the_models_folder_the_user_chose(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.update(StorageConfig(models_dir=tmp_path / "big-disk"))
    paths = engine_paths("whispercpp-large-v3-turbo", storage)
    assert tmp_path / "big-disk" in paths.model.parents
    assert paths.binary.is_relative_to(tmp_path / "data" / "runtimes")


def test_engine_paths_reject_an_unknown_engine(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown ASR engine"):
        engine_paths("nope", Storage(tmp_path))


def test_cli_prints_ascii_json_that_round_trips() -> None:
    segment = segment_of([Word("naïve", 0, 10), Word("café。", 10, 20)], 0, 20)
    text = cli.segments_json("whispercpp-large-v3-turbo", [segment])
    assert text.isascii()
    parsed = json.loads(text)
    assert parsed["segments"][0]["words"][1] == {"text": "café。", "start_ms": 10, "end_ms": 20}


def test_cli_reports_a_missing_binary_with_a_chinese_path_without_crashing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli.main(
        "whispercpp-large-v3-turbo",
        [str(WAV_15S), "--bin", str(tmp_path / "不存在" / "whisper-cli.exe"), "--model", "m.bin"],
    )
    assert code == 1
    assert "binary not found" in capsys.readouterr().err


class StubEngine:
    id = "stub"
    supports_word_timestamps = True

    def __init__(self, per_chunk: Sequence[Sequence[Word]]) -> None:
        self.per_chunk = per_chunk
        self.received: list[tuple[str, float]] = []

    def is_available(self) -> bool:
        return True

    def transcribe(
        self,
        wav_path: Path,
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[Segment]:
        return self.transcribe_many([wav_path], language, progress_cb, cancel)[0]

    def transcribe_many(
        self,
        wav_paths: Sequence[Path],
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[list[Segment]]:
        for path in wav_paths:
            with wave.open(str(path), "rb") as reader:
                self.received.append((path.name, reader.getnframes() / SAMPLE_RATE))
        return [[segment_of(words, 0, 0)] if words else [] for words in self.per_chunk]


def w(text: str, start: int, end: int) -> Word:
    return Word(text, start, end)


def texts(words: Sequence[Word]) -> list[str]:
    return [x.text for x in words]


def test_chunks_are_cut_from_the_wav_and_words_move_to_wav_time() -> None:
    engine = StubEngine([[w("one", 100, 400)], [w("two", 50, 300)]])
    chunks = [Chunk(1000, 4000), Chunk(6000, 9500)]
    words = transcribe_chunks(engine, WAV_15S, chunks)
    assert [(x.text, x.start_ms, x.end_ms) for x in words] == [
        ("one", 1100, 1400),
        ("two", 6050, 6300),
    ]
    assert engine.received == [("c00000.wav", 3.0), ("c00001.wav", 3.5)]


def test_chunk_wavs_are_ascii_named_and_removed_afterwards() -> None:
    seen: list[Path] = []

    class Spy(StubEngine):
        def transcribe_many(
            self,
            wav_paths: Sequence[Path],
            language: str = "en",
            progress_cb: ProgressCb | None = None,
            cancel: threading.Event | None = None,
        ) -> list[list[Segment]]:
            seen.extend(wav_paths)
            return super().transcribe_many(wav_paths, language, progress_cb, cancel)

    transcribe_chunks(Spy([[w("a", 0, 10)]]), WAV_15S, [Chunk(0, 2000)])
    assert seen
    assert all(str(p).isascii() for p in seen)
    assert not any(p.exists() for p in seen)


def test_overlap_is_cut_at_its_middle_so_the_whole_word_wins() -> None:
    chunks = [Chunk(0, 10_000), Chunk(9600, 20_000)]
    per_chunk = [
        [w("this", 9000, 9300), w("import", 9650, 9990)],
        [w("important", 9650, 10_300), w("thing", 10_400, 10_800)],
    ]
    kept = trim_overlaps(chunks, per_chunk)
    assert texts(kept[0]) == ["this"]
    assert texts(kept[1]) == ["important", "thing"]


def test_chunks_that_do_not_overlap_keep_every_word() -> None:
    chunks = [Chunk(0, 5000), Chunk(5000, 9000), Chunk(12_000, 15_000)]
    per_chunk = [[w("a", 4900, 5100)], [w("b", 5200, 5300)], [w("c", 12_100, 12_200)]]
    assert trim_overlaps(chunks, per_chunk) == per_chunk


def spaced(count: int, gap_ms: int) -> list[Chunk]:
    return [Chunk(i * (900 + gap_ms), i * (900 + gap_ms) + 900) for i in range(count)]


def test_a_period_at_a_chunk_edge_inside_running_speech_is_removed() -> None:
    words = [
        [w("use", 0, 200), w("that", 250, 500), w("to", 520, 600), w("make.", 650, 900)],
        [w("Really", 1100, 1500), w("good", 1500, 1800), w("decisions.", 1800, 2400)],
    ]
    repaired = repair_boundaries(spaced(2, 100), words)
    assert texts(repaired[0])[-1] == "make"
    assert texts(repaired[1]) == ["really", "good", "decisions."]


def test_a_period_before_a_long_pause_is_kept() -> None:
    words = [[w("done.", 0, 400)], [w("Next", 1400, 1800), w("topic", 1800, 2100)]]
    assert repair_boundaries(spaced(2, 150), words) == words


def test_true_sentence_ends_seen_in_a_real_talk_keep_their_period() -> None:
    for tail, head, gap_ms in (("fit.", "But", 298), ("works.", "But", 266), ("piece.", "I", 186)):
        words = [[w(tail, 0, 400)], [w(head, 700, 900)]]
        assert repair_boundaries(spaced(2, gap_ms), words) == words


def test_a_filler_after_a_period_is_not_a_continuation() -> None:
    words = [[w("correctly.", 0, 400)], [w("uh", 1300, 1400), w("so", 1400, 1500)]]
    assert repair_boundaries(spaced(2, 714), words) == words


def test_a_filler_head_keeps_its_capital_when_the_period_before_it_goes() -> None:
    words = [[w("and", 0, 100), w("so.", 100, 400)], [w("Uh,", 450, 600), w("fine", 600, 900)]]
    repaired = repair_boundaries(spaced(2, 50), words)
    assert texts(repaired[0]) == ["and", "so"]
    assert texts(repaired[1]) == ["Uh,", "fine"]


def test_a_period_before_a_lowercase_word_is_removed_even_after_a_pause() -> None:
    repaired = repair_boundaries(spaced(2, 900), [[w("and.", 0, 400)], [w("then", 1400, 1800)]])
    assert texts(repaired[0]) == ["and"]
    assert texts(repaired[1]) == ["then"]


def test_a_period_after_a_stopword_goes_and_the_next_word_keeps_its_capital() -> None:
    for tail in ("and.", "um.", "the."):
        words = [[w(tail, 0, 400)], [w("You", 1900, 2200), w("can", 2200, 2400)]]
        repaired = repair_boundaries(spaced(2, 900), words)
        assert texts(repaired[0]) == [tail[:-1]]
        assert texts(repaired[1]) == ["You", "can"]


def test_names_and_the_pronoun_i_keep_their_capital_at_a_repaired_edge() -> None:
    mid_sentence = [w("we", 0, 100), w("use", 100, 200), w("Cursor", 200, 400)]
    for first in ("Cursor", "I", "I'm", "GitHub"):
        words = [
            mid_sentence,
            [w("so.", 3000, 3300)],
            [w(first, 3400, 3700), w("agree", 3700, 4000)],
        ]
        assert texts(repair_boundaries(spaced(3, 100), words)[2])[0] == first
    they = [[w("so.", 0, 300)], [w("They", 400, 700)]]
    assert texts(repair_boundaries(spaced(2, 100), they)[1]) == ["they"]


def test_a_lowercase_pronoun_i_is_capitalized() -> None:
    words = [[w("i'm", 0, 300), w("sure", 300, 600), w("i", 600, 700), w("think", 700, 900)]]
    assert texts(capitalize_pronoun_i(words[0])) == ["I'm", "sure", "I", "think"]
    assert texts(capitalize_pronoun_i([w("idea", 0, 300), w("in", 300, 400)])) == ["idea", "in"]


def test_question_marks_and_ellipses_at_an_edge_stay() -> None:
    for tail in ("why?", "wait...", "yes!"):
        words = [[w(tail, 0, 300)], [w("Next", 350, 600)]]
        assert repair_boundaries(spaced(2, 100), words) == words


def test_empty_chunks_are_skipped_when_repairing_and_merging() -> None:
    engine = StubEngine([[w("a.", 0, 200)], [], [w("b", 300, 500)]])
    words = transcribe_chunks(
        engine, WAV_15S, [Chunk(0, 1000), Chunk(1000, 2000), Chunk(2000, 3000)]
    )
    assert texts(words) == ["a", "b"]


def test_merged_words_are_in_time_order_and_feed_the_segmenter() -> None:
    engine = StubEngine(
        [
            [w("so", 0, 300), w("we", 350, 500), w("shipped.", 600, 1100)],
            [w("Two", 100, 400), w("thousand", 450, 1000), w("PRs.", 1050, 1500)],
        ]
    )
    words = transcribe_chunks(engine, WAV_15S, [Chunk(0, 3000), Chunk(4000, 7000)])
    assert texts(words) == ["so", "we", "shipped.", "Two", "thousand", "PRs."]
    assert [x.start_ms for x in words] == sorted(x.start_ms for x in words)
    cues = to_cues([segment_of(words, words[0].start_ms, words[-1].end_ms)])
    assert [c.src for c in cues] == ["so we shipped.", "Two thousand PRs."]


def test_an_engine_without_word_timestamps_is_refused() -> None:
    engine = StubEngine([[]])
    engine.supports_word_timestamps = False
    with pytest.raises(EngineError, match="no word timestamps"):
        transcribe_chunks(engine, WAV_15S, [Chunk(0, 1000)])


def test_a_chunk_past_the_end_of_the_wav_is_refused() -> None:
    with pytest.raises(ValueError, match="past the"):
        transcribe_chunks(StubEngine([[]]), WAV_15S, [Chunk(0, 30_000)])
