import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness import Segment, Word, run_engine, sibling, to_wav

ENGINE = "whispercpp-large-v3-turbo"


def words_from_tokens(tokens: list[dict[str, Any]]) -> list[Word]:
    words: list[Word] = []
    for token in tokens:
        text: str = token["text"]
        if text.startswith("[_"):
            continue
        start = token["offsets"]["from"] / 1000
        end = token["offsets"]["to"] / 1000
        if words and not text.startswith(" "):
            words[-1].text += text
            words[-1].end = end
        elif text.strip():
            words.append(Word(text.strip(), start, end))
    return words


def parse(out_base: Path) -> list[Segment]:
    raw = sibling(out_base, ".json").read_text(encoding="utf-8", errors="replace")
    return [
        Segment(
            text=item["text"].strip(),
            start=item["offsets"]["from"] / 1000,
            end=item["offsets"]["to"] / 1000,
            words=words_from_tokens(item.get("tokens", [])),
        )
        for item in json.loads(raw)["transcription"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run whisper.cpp large-v3-turbo on one talk.")
    parser.add_argument("audio", type=Path, help="video or 16 kHz mono wav")
    parser.add_argument("--bin", type=Path, required=True, help="whisper-cli.exe")
    parser.add_argument("--model", type=Path, required=True, help="ggml-large-v3-turbo.bin")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="r1")
    args = parser.parse_args()

    wav = to_wav(args.audio, args.out_dir)
    out_base = args.out_dir / f"whispercpp-{wav.stem}-{args.run_id}"
    command = [str(args.bin), "-m", str(args.model), "-f", str(wav), "-l", "en"]
    command += ["-osrt", "-ojf", "-of", str(out_base)]
    record = run_engine(ENGINE, command, wav, out_base, parse)
    return record.exit_code


if __name__ == "__main__":
    sys.exit(main())
