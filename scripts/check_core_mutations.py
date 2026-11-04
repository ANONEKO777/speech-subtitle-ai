from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "backend" / "core"
AUDIO, VAD, SEG = CORE / "audio.py", CORE / "vad.py", CORE / "segmenter.py"


@dataclass(frozen=True)
class Mutation:
    name: str
    path: Path
    old: str
    new: str


MUTATIONS = [
    Mutation(
        "vad: previous-window context dropped",
        VAD,
        "context = buffer[-CONTEXT_SAMPLES:]",
        "context = np.zeros(CONTEXT_SAMPLES, dtype=np.float32)",
    ),
    Mutation("vad: 10x input gain", VAD, "/ 32768.0", "/ 3276.8"),
    Mutation(
        "vad: no hysteresis", VAD, "elif p < params.neg_threshold:", "elif p < params.threshold:"
    ),
    Mutation(
        "vad: short silences not merged",
        VAD,
        "if merged and start - merged[-1][1] < params.min_silence_ms:",
        "if False:",
    ),
    Mutation(
        "vad: no pad after the last speech",
        VAD,
        "last_end = min(total_ms, last_speech_end + pad)",
        "last_end = min(total_ms, last_speech_end)",
    ),
    Mutation(
        "vad: no pad before an onset",
        VAD,
        "return max(position, runs[k][0] - pad)",
        "return max(position, runs[k][0])",
    ),
    Mutation(
        "vad: no anti-sliver clamp",
        VAD,
        "hi = min(hi, last_end - params.min_chunk_ms)",
        "pass",
    ),
    Mutation(
        "vad: cut at the start of the silence",
        VAD,
        "cut = (max(best_gap[0], lo) + min(best_gap[1], hi)) // 2",
        "cut = max(best_gap[0], lo)",
    ),
    Mutation(
        "vad: long silence stays inside the chunk",
        VAD,
        "if g_end - g_start >= params.long_silence_ms:",
        "if False:",
    ),
    Mutation(
        "audio: ffmpeg leaves its partial file after a failure",
        AUDIO,
        "        partial.unlink(missing_ok=True)\n",
        "        pass\n",
    ),
    Mutation(
        "audio: ffprobe failure ignored",
        AUDIO,
        '    if proc.returncode != 0:\n        raise AudioError(f"ffprobe could not read',
        '    if False:\n        raise AudioError(f"ffprobe could not read',
    ),
    Mutation(
        "audio: PATH folder beats tool_dir",
        AUDIO,
        "(tool_dir, env_dir and Path(env_dir))",
        "(env_dir and Path(env_dir), tool_dir)",
    ),
    Mutation("audio: every audio track mapped", AUDIO, '"0:a:0",', '"0:a",'),
    Mutation("audio: size left out of the stamp", AUDIO, '"size": stat.st_size, ', ""),
    Mutation(
        "audio: stamp taken after ffmpeg",
        AUDIO,
        "write_text_file(_stamp_path(wav), json.dumps(stamp))",
        "write_text_file(_stamp_path(wav), json.dumps(_source_stamp(video)))",
    ),
    Mutation("audio: partial not fsynced", AUDIO, "        _flush_to_disk(partial)\n", ""),
    Mutation(
        "audio: cut-short wav accepted",
        AUDIO,
        "if actual < promised:",
        "if False:",
    ),
    Mutation(
        "audio: relative video path handed to ffprobe",
        AUDIO,
        '"csv=p=0",\n            str(video.absolute()),',
        '"csv=p=0",\n            str(video),',
    ),
    Mutation("audio: timeout ignored", AUDIO, "if wait <= 0:", "if False:"),
    Mutation(
        "audio: cancel ignored",
        AUDIO,
        "if cancel is not None and cancel.is_set():",
        "if False:",
    ),
    Mutation(
        "segmenter: duplicate tolerance 0", SEG, "_DUP_TOLERANCE_MS = 100", "_DUP_TOLERANCE_MS = 0"
    ),
    Mutation(
        "segmenter: overlap majority rule removed",
        SEG,
        "return word.end_ms > word.start_ms and covered * 2 >= word.end_ms - word.start_ms",
        "return False",
    ),
    Mutation(
        "segmenter: matched words still count as cover",
        SEG,
        "        if index not in taken:\n            covered",
        "        if True:\n            covered",
    ),
    Mutation(
        "segmenter: every segment pair deduplicated",
        SEG,
        "if kept and first < reach else []",
        "if kept else []",
    ),
    Mutation(
        "segmenter: word cap anchored at its start",
        SEG,
        "start, end = max(word.start_ms, word.end_ms - _MAX_WORD_MS), word.end_ms",
        "start, end = word.start_ms, min(word.end_ms, word.start_ms + _MAX_WORD_MS)",
    ),
    Mutation(
        "segmenter: late glue token stretches the word",
        SEG,
        "joined = end if start - prev.end_ms <= _GLUE_GAP_MS else prev.end_ms",
        "joined = end",
    ),
    Mutation(
        "segmenter: closers hide a sentence end",
        SEG,
        "return (text.rstrip(_CLOSERS) or text)[-1]",
        "return text[-1]",
    ),
    Mutation(
        "segmenter: violations ignores ids",
        SEG,
        "if index and cue.id <= cues[index - 1].id:",
        "if False:",
    ),
    Mutation(
        "segmenter: sentence end costs as much as no punctuation",
        SEG,
        "cost = 0.0 if last in _SENTENCE_END else 1.5 if last in _CLAUSE_END else 4.0",
        "cost = 4.0 if last in _SENTENCE_END else 1.5 if last in _CLAUSE_END else 4.0",
    ),
    Mutation(
        "segmenter: clause end costs as much as no punctuation",
        SEG,
        "cost = 0.0 if last in _SENTENCE_END else 1.5 if last in _CLAUSE_END else 4.0",
        "cost = 0.0 if last in _SENTENCE_END else 4.0",
    ),
]


def killing_tests() -> list[str] | None:
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--maxfail=50"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "VST_REQUIRE_ASSETS": "1"},
    )
    if run.returncode == 0:
        return None
    return [line.split(" - ")[0] for line in run.stdout.splitlines() if line.startswith("FAILED ")]


def main() -> int:
    wanted = sys.argv[1:]
    mutations = [m for m in MUTATIONS if not wanted or any(w in m.name for w in wanted)]
    originals = {path: path.read_bytes() for path in {m.path for m in mutations}}
    survivors = 0
    try:
        for mutation in mutations:
            source = originals[mutation.path].decode("utf-8")
            if source.count(mutation.old) != 1:
                print(f"STALE     {mutation.name}: anchor text not found exactly once")
                survivors += 1
                continue
            mutation.path.write_bytes(source.replace(mutation.old, mutation.new).encode("utf-8"))
            failed = killing_tests()
            mutation.path.write_bytes(originals[mutation.path])
            if failed is None:
                print(f"SURVIVED  {mutation.name}")
                survivors += 1
            else:
                print(f"killed    {mutation.name} ({len(failed)} failing, e.g. {failed[0][7:]})")
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
    print(f"{len(mutations) - survivors}/{len(mutations)} mutations killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
