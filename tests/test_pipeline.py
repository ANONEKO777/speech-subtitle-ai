from __future__ import annotations

import json
import os
import re
import shutil
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from test_summarize import good_map, good_reduce

from backend.core.model import Step, StepStatus, Word
from backend.core.pipeline import (
    STEPS,
    Cancelled,
    LlmSession,
    PipelineError,
    Ports,
    Progress,
    Settings,
    derive_key,
    run,
)
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file
from backend.core.vad import Chunk
from backend.engines.whispercpp import WhisperCppEngine
from backend.llm.client import LlmError, Message

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden" / "en_15s"
UPDATE_ENV = "VST_UPDATE_GOLDEN"
GOLDEN_FILES = (
    "chunks.json",
    "segments.json",
    "subs.en.json",
    "subs.zh-TW.json",
    "en.srt",
    "zh-TW.srt",
    "bilingual.ass",
    "bilingual.vtt",
    "summary.md",
)
SETTINGS = Settings(
    asr_engine="whispercpp-large-v3-turbo",
    asr_identity="whisper@1",
    vad_identity="silero@1",
    llm_identity="llm-a",
)


def asr_words() -> list[Word]:
    engine = WhisperCppEngine(Path("whisper-cli"), Path("model.bin"))
    segments = engine.parse(FIXTURES / "engines" / "whisper_15s.json")
    return [w for segment in segments for w in segment.words or ()]


def talk_words(sentences: int) -> list[Word]:
    words: list[Word] = []
    for n in range(sentences):
        start = n * 3000
        for i, text in enumerate(("Sentence", f"number{'x' * n}", "is", "here.")):
            words.append(Word(text, start + i * 400, start + i * 400 + 380))
    return words


def translation_reply(messages: Sequence[Message], mark: str) -> str:
    entries = json.loads(messages[1]["content"])["translate"]
    out: list[dict[str, object]] = []
    for entry in entries:
        pieces = re.split(r"(\[\[\d+\]\])", entry["en"])
        zh = "".join(
            piece if re.fullmatch(r"\[\[\d+\]\]", piece) else mark * max(2, len(piece) // 4)
            for piece in pieces
            if piece.strip() or re.fullmatch(r"\[\[\d+\]\]", piece)
        )
        out.append({"id": entry["id"], "zh": zh + "。"})
    return json.dumps({"translations": out}, ensure_ascii=False)


@dataclass(slots=True)
class Fakes:
    """Counts what the pipeline asks of the outside world."""

    mark: str = "譯"
    extracted: int = 0
    split: int = 0
    transcribed: int = 0
    llm_opened: int = 0
    llm_closed: int = 0
    translate_calls: int = 0
    fail_translate_after: int | None = None
    transcribe_error: BaseException | None = None
    words: list[Word] | None = None
    cancel_in_asr: threading.Event | None = None
    asked: list[str] = field(default_factory=list[str])

    def ports(self) -> Ports:
        return Ports(self.extract_audio, self.split_vad, self.transcribe, self.open_llm)

    def extract_audio(self, video: Path, wav: Path, cancel: threading.Event) -> None:
        self.extracted += 1
        shutil.copyfile(FIXTURES / "en_15s.wav", wav)

    def split_vad(self, wav: Path) -> list[Chunk]:
        self.split += 1
        return [Chunk(0, 15_000)]

    def transcribe(
        self,
        wav: Path,
        chunks: Sequence[Chunk],
        progress: Callable[[float], None],
        cancel: threading.Event,
    ) -> list[Word]:
        self.transcribed += 1
        progress(0.5)
        if self.cancel_in_asr is not None:
            self.cancel_in_asr.set()
            progress(0.6)
        if self.transcribe_error is not None:
            raise self.transcribe_error
        return self.words or asr_words()

    @contextmanager
    def open_llm(self, cancel: threading.Event) -> Generator[LlmSession]:
        self.llm_opened += 1
        try:
            yield LlmSession(self.translate, self.summarize)
        finally:
            self.llm_closed += 1

    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        self.translate_calls += 1
        if (
            self.fail_translate_after is not None
            and self.translate_calls > self.fail_translate_after
        ):
            raise LlmError("the server went away", retryable=False)
        self.asked.append(messages[1]["content"])
        return translation_reply(messages, self.mark)

    def summarize(self, messages: Sequence[Message], temperature: float) -> str:
        if messages[1]["content"].startswith("Part "):
            return good_map(messages)
        return good_reduce(messages, "zh-TW")


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "talk.mp4"
    path.write_bytes(b"not a real video")
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "project"


def steps_of(folder: Path) -> dict[str, tuple[StepStatus, str | None]]:
    project = parse_project(read_text_file(folder / "project.json"))
    return {step.value: (state.status, state.key) for step, state in project.steps.items()}


def test_a_full_run_writes_every_output_and_matches_the_golden_sample(
    video: Path, folder: Path
) -> None:
    fakes = Fakes()
    report = run(video, folder, SETTINGS, fakes.ports())
    assert report.ran == tuple(Step)
    if os.environ.get(UPDATE_ENV) == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for name in GOLDEN_FILES:
            shutil.copyfile(folder / name, GOLDEN / name)
    for name in GOLDEN_FILES:
        assert (folder / name).read_bytes() == (GOLDEN / name).read_bytes(), name
    assert all(status is StepStatus.DONE and key for status, key in steps_of(folder).values())


def test_the_outputs_have_matching_cues_and_no_overlap(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
    english = parse_subs(read_text_file(folder / "subs.en.json"))
    assert [c.id for c in cues] == [c.id for c in english]
    assert all(c.zh for c in cues)
    assert all(a.end_ms <= b.start_ms for a, b in zip(cues, cues[1:], strict=False))


def test_a_second_run_with_nothing_changed_does_no_work(video: Path, folder: Path) -> None:
    fakes = Fakes()
    run(video, folder, SETTINGS, fakes.ports())
    before = (fakes.extracted, fakes.split, fakes.transcribed, fakes.llm_opened)
    second = run(video, folder, SETTINGS, fakes.ports())
    assert second.ran == ()
    assert (fakes.extracted, fakes.split, fakes.transcribed, fakes.llm_opened) == before


def test_a_new_llm_reruns_only_the_steps_downstream_of_it(video: Path, folder: Path) -> None:
    fakes = Fakes(mark="譯")
    run(video, folder, SETTINGS, fakes.ports())
    first = (folder / "subs.zh-TW.json").read_text(encoding="utf-8")
    swapped = Fakes(mark="改")
    report = run(video, folder, replace(SETTINGS, llm_identity="llm-b"), swapped.ports())
    assert report.ran == (Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)
    assert (swapped.extracted, swapped.split, swapped.transcribed) == (0, 0, 0)
    second = (folder / "subs.zh-TW.json").read_text(encoding="utf-8")
    assert second != first
    assert "譯" not in second
    assert "改" in second


def test_a_new_asr_model_reruns_asr_and_everything_after_it(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    fakes = Fakes()
    report = run(video, folder, replace(SETTINGS, asr_identity="whisper@2"), fakes.ports())
    assert report.ran == (Step.ASR, Step.SEGMENT, Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)
    assert (fakes.extracted, fakes.split) == (0, 0)


def test_a_new_summary_language_reruns_only_the_summary(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    fakes = Fakes()
    report = run(video, folder, replace(SETTINGS, summary_langs=("zh-TW", "en")), fakes.ports())
    assert report.ran == (Step.SUMMARIZE,)
    assert fakes.translate_calls == 0
    assert (folder / "summary.en.md").is_file()


def test_a_missing_output_reruns_its_step_and_what_reads_it(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    (folder / "en.srt").unlink()
    fakes = Fakes()
    assert run(video, folder, SETTINGS, fakes.ports()).ran == (Step.EXPORT,)
    (folder / "subs.en.json").unlink()
    assert run(video, folder, SETTINGS, fakes.ports()).ran == (
        Step.SEGMENT,
        Step.TRANSLATE,
        Step.EXPORT,
        Step.SUMMARIZE,
    )


def test_a_changed_video_starts_over(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    video.write_bytes(b"a different, longer video file")
    assert run(video, folder, SETTINGS, Fakes().ports()).ran == tuple(Step)


def test_ctrl_c_during_asr_then_a_rerun_resumes_at_asr(video: Path, folder: Path) -> None:
    interrupted = Fakes(transcribe_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(video, folder, SETTINGS, interrupted.ports())
    state = steps_of(folder)
    assert state["audio"][0] is StepStatus.DONE
    assert state["vad"][0] is StepStatus.DONE
    assert state["asr"][0] is StepStatus.FAILED
    assert state["translate"][0] is StepStatus.PENDING
    assert interrupted.llm_opened == 0

    fakes = Fakes()
    report = run(video, folder, SETTINGS, fakes.ports())
    assert report.ran == (
        Step.ASR,
        Step.SEGMENT,
        Step.TRANSLATE,
        Step.EXPORT,
        Step.SUMMARIZE,
    )
    assert (fakes.extracted, fakes.split) == (0, 0)
    assert (folder / "summary.md").is_file()


def test_the_cancel_event_stops_a_run_and_a_rerun_resumes(video: Path, folder: Path) -> None:
    cancel = threading.Event()
    fakes = Fakes(cancel_in_asr=cancel)
    with pytest.raises(Cancelled):
        run(video, folder, SETTINGS, fakes.ports(), cancel=cancel)
    assert steps_of(folder)["asr"][0] is StepStatus.FAILED
    assert run(video, folder, SETTINGS, Fakes().ports()).ran[0] is Step.ASR


def test_a_step_error_is_named_and_recorded(video: Path, folder: Path) -> None:
    fakes = Fakes(transcribe_error=RuntimeError("engine blew up"))
    with pytest.raises(PipelineError, match="asr: engine blew up") as caught:
        run(video, folder, SETTINGS, fakes.ports())
    assert caught.value.step is Step.ASR
    project = parse_project(read_text_file(folder / "project.json"))
    assert project.steps[Step.ASR].error == "RuntimeError: engine blew up"


def no_words(
    wav: Path, chunks: Sequence[Chunk], progress: Callable[[float], None], cancel: threading.Event
) -> list[Word]:
    return []


def test_no_words_is_an_error_not_an_empty_subtitle(video: Path, folder: Path) -> None:
    fakes = Fakes()
    ports = replace(fakes.ports(), transcribe=no_words)
    with pytest.raises(PipelineError, match="no speech"):
        run(video, folder, SETTINGS, ports)


def test_the_llm_opens_once_for_both_steps_and_closes_when_the_run_ends(
    video: Path, folder: Path
) -> None:
    fakes = Fakes()
    run(video, folder, SETTINGS, fakes.ports())
    assert (fakes.llm_opened, fakes.llm_closed) == (1, 1)


def test_the_llm_closes_when_translation_fails(video: Path, folder: Path) -> None:
    fakes = Fakes(fail_translate_after=0)
    with pytest.raises(PipelineError):
        run(video, folder, SETTINGS, fakes.ports())
    assert (fakes.llm_opened, fakes.llm_closed) == (1, 1)


def test_the_llm_never_opens_while_asr_runs(video: Path, folder: Path) -> None:
    seen: list[int] = []
    fakes = Fakes()
    ports = fakes.ports()

    def transcribe(*args: object) -> list[Word]:
        seen.append(fakes.llm_opened - fakes.llm_closed)
        return asr_words()

    run(video, folder, SETTINGS, replace(ports, transcribe=transcribe))  # type: ignore[arg-type]
    assert seen == [0]


def test_translation_resumes_under_the_same_key_and_restarts_under_a_new_one(
    video: Path, folder: Path
) -> None:
    small = replace(SETTINGS, batch_size=2)
    broken = Fakes(fail_translate_after=2, words=talk_words(8))
    with pytest.raises(PipelineError):
        run(video, folder, small, broken.ports())
    kept = [c for c in parse_subs(read_text_file(folder / "subs.zh-TW.json")) if c.zh]
    assert 0 < len(kept) < len(parse_subs(read_text_file(folder / "subs.en.json")))

    resumed = Fakes(words=talk_words(8))
    run(video, folder, small, resumed.ports())
    fresh = Fakes(words=talk_words(8))
    run(video, folder.parent / "fresh", small, fresh.ports())
    assert resumed.translate_calls == fresh.translate_calls - 2
    cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
    assert all(c.zh for c in cues)

    other = Fakes(fail_translate_after=1, mark="改", words=talk_words(8))
    with pytest.raises(PipelineError):
        run(video, folder, replace(small, llm_identity="llm-b"), other.ports())
    left = [c.zh for c in parse_subs(read_text_file(folder / "subs.zh-TW.json")) if c.zh]
    assert left
    assert all("譯" not in zh for zh in left)


def test_progress_reports_each_step_from_start_to_cached_or_done(video: Path, folder: Path) -> None:
    first: list[Progress] = []
    second: list[Progress] = []
    run(video, folder, SETTINGS, Fakes().ports(), progress=first.append)
    run(video, folder, SETTINGS, Fakes().ports(), progress=second.append)
    assert {p.step for p in first} == set(Step)
    assert [p.message for p in second] == ["cached"] * len(Step)
    asr = [p.fraction for p in first if p.step is Step.ASR]
    assert asr[0] == 0.0 and asr[-1] == 1.0 and asr == sorted(asr)


def test_the_report_adds_up_to_the_total_and_overhead_is_small(video: Path, folder: Path) -> None:
    report = run(video, folder, SETTINGS, Fakes().ports())
    assert report.overhead_s >= 0
    assert report.overhead_s < 2.0
    assert "overhead" in report.describe()
    assert run(video, folder, SETTINGS, Fakes().ports()).total_s < 1.0


def test_keys_change_with_exactly_what_a_step_reads() -> None:
    def keys(settings: Settings, video: str = "1:1") -> dict[Step, str]:
        out: dict[Step, str] = {}
        for spec in STEPS:
            out[spec.step] = derive_key(spec, settings, video, out)
        return out

    base = keys(SETTINGS)
    assert keys(SETTINGS) == base
    llm = keys(replace(SETTINGS, llm_identity="x"))
    assert {s for s in Step if llm[s] != base[s]} == {Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE}
    asr = keys(replace(SETTINGS, asr_identity="x"))
    assert {s for s in Step if asr[s] == base[s]} == {Step.AUDIO, Step.VAD}
    video = keys(SETTINGS, "2:2")
    assert all(video[s] != base[s] for s in Step)
    vad = keys(replace(SETTINGS, vad_identity="x"))
    assert {s for s in Step if vad[s] == base[s]} == {Step.AUDIO}


def test_every_step_is_in_the_table_in_order() -> None:
    assert [spec.step for spec in STEPS] == list(Step)
    names = [out.value for spec in STEPS for out in spec.outputs(SETTINGS)]
    assert len(names) == len(set(names))


def test_project_json_keeps_the_video_path_and_a_key_per_step(video: Path, folder: Path) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    project = parse_project(read_text_file(folder / "project.json"))
    assert Path(project.video_path) == video.absolute()
    assert all(state.key and len(state.key) == 32 for state in project.steps.values())


def test_dropping_the_english_summary_with_a_new_llm_leaves_no_old_summary(
    video: Path, folder: Path
) -> None:
    both = replace(SETTINGS, summary_langs=("zh-TW", "en"))
    run(video, folder, both, Fakes().ports())
    assert (folder / "summary.en.md").is_file()
    run(video, folder, replace(SETTINGS, llm_identity="llm-b"), Fakes().ports())
    assert not (folder / "summary.en.md").exists()


def test_the_llm_never_starts_when_every_answer_is_already_stored(
    video: Path, folder: Path
) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    (folder / "summary.md").unlink()
    (folder / "subs.en.json").unlink()
    fakes = Fakes()
    report = run(video, folder, SETTINGS, fakes.ports())
    assert Step.TRANSLATE in report.ran and Step.SUMMARIZE in report.ran
    assert fakes.llm_opened == 0
    assert (folder / "summary.md").is_file()


def test_a_failed_translate_does_not_leave_export_and_summarize_marked_done(
    video: Path, folder: Path
) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    broken = Fakes(fail_translate_after=0)
    with pytest.raises(PipelineError):
        run(video, folder, replace(SETTINGS, llm_identity="llm-b"), broken.ports())
    state = steps_of(folder)
    assert state["translate"][0] is StepStatus.FAILED
    assert state["export"][0] is StepStatus.PENDING
    assert state["summarize"][0] is StepStatus.PENDING
    assert state["asr"][0] is StepStatus.DONE
    assert not (folder / "zh-TW.srt").exists()
    assert not (folder / "summary.md").exists()


def test_a_step_that_stopped_halfway_leaves_the_steps_after_it_pending(
    video: Path, folder: Path
) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    (folder / "segments.json").unlink()
    with pytest.raises(KeyboardInterrupt):
        run(video, folder, SETTINGS, Fakes(transcribe_error=KeyboardInterrupt()).ports())
    state = steps_of(folder)
    assert state["asr"][0] is StepStatus.FAILED
    assert all(state[name][0] is StepStatus.PENDING for name in ("segment", "translate", "export"))
