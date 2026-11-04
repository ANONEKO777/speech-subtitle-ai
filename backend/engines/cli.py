from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.core.audio import AudioError
from backend.core.model import Segment
from backend.engines.base import EngineError
from backend.engines.table import create_engine, engine_paths
from backend.manager.profiles import Device
from backend.manager.storage import Storage, default_user_data


def segments_json(engine_id: str, segments: Sequence[Segment]) -> str:
    payload = {
        "engine": engine_id,
        "segments": [
            {
                "text": s.text,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "words": [
                    {"text": w.text, "start_ms": w.start_ms, "end_ms": w.end_ms}
                    for w in s.words or ()
                ],
            }
            for s in segments
        ],
    }
    return json.dumps(payload, indent=1)


def main(engine_id: str, argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=f"Transcribe one wav with {engine_id}.")
    parser.add_argument("wav", type=Path)
    parser.add_argument("--bin", type=Path, help="engine executable")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--aligner", type=Path)
    parser.add_argument("--user-data", type=Path, help="the app's data folder (VST_USER_DATA)")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout", type=float)
    args = parser.parse_args(argv)

    found = engine_paths(engine_id, Storage(args.user_data or default_user_data()))
    binary, model = args.bin or found.binary, args.model or found.model
    aligner = args.aligner or found.aligner
    engine = create_engine(
        engine_id,
        binary,
        model,
        aligner=aligner,
        device=Device.CPU if args.cpu else Device.CUDA,
        timeout_s=args.timeout,
    )

    def report(fraction: float) -> None:
        print(f"progress {fraction:.0%}", file=sys.stderr)

    try:
        segments = engine.transcribe(args.wav, args.language, report)
    except (EngineError, AudioError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    print(segments_json(engine_id, segments))
    return 0
