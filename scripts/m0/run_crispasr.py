import argparse
import json
import sys
from pathlib import Path

from harness import Segment, Word, run_engine, sibling, to_wav

ENGINE = "crispasr-qwen3-asr-1.7b"


def parse(out_base: Path) -> list[Segment]:
    raw = sibling(out_base, ".json").read_text(encoding="utf-8", errors="replace")
    return [
        Segment(
            text=item["text"].strip(),
            start=item["offsets"]["from"] / 1000,
            end=item["offsets"]["to"] / 1000,
            words=[
                Word(w["text"].strip(), w["offsets"]["from"] / 1000, w["offsets"]["to"] / 1000)
                for w in item.get("words", [])
                if w["text"].strip()
            ],
        )
        for item in json.loads(raw)["transcription"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CrispASR Qwen3-ASR-1.7B with Qwen3-ForcedAligner on one talk."
    )
    parser.add_argument("audio", type=Path, help="video or 16 kHz mono wav")
    parser.add_argument("--bin", type=Path, required=True, help="crispasr.exe")
    parser.add_argument("--model", type=Path, required=True, help="qwen3-asr-1.7b GGUF")
    parser.add_argument("--aligner", type=Path, required=True, help="qwen3-forced-aligner GGUF")
    parser.add_argument("--vad-model", type=Path, required=True, help="silero VAD ggml file")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="r1")
    args = parser.parse_args()

    passed = [args.bin, args.model, args.aligner, args.vad_model, args.out_dir, args.run_id]
    non_ascii = [str(arg) for arg in passed if not str(arg).isascii()]
    if non_ascii:
        raise SystemExit(f"crispasr.exe v0.8.49 cannot open non-ASCII paths: {non_ascii}")

    wav = to_wav(args.audio, args.out_dir)
    out_base = args.out_dir / f"crispasr-{wav.stem}-{args.run_id}"
    command = [str(args.bin), "--backend", "qwen3", "-m", str(args.model), "-f", str(wav)]
    command += ["-l", "en", "-am", str(args.aligner), "--vad", "-vm", str(args.vad_model)]
    command += ["--strict-pipeline", "-osrt", "-ojf", "-of", str(out_base)]
    record = run_engine(ENGINE, command, wav, out_base, parse)
    return record.exit_code


if __name__ == "__main__":
    sys.exit(main())
