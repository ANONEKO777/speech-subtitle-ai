"""Translate the sampled units of the P25 evidence into the targets of the Japanese route, with the
translation step the app runs (`translate.run` with the registry's own source and target rows, the
default glossary and the retries of the pipeline). It is the P25 harness's sampling and server, not
its prompts: the harness's `GENERIC_JA` is not used.

    python scripts/p26a_real_run.py OUT --targets en zh-CN ko

`OUT` holds the `units.json` that `scripts/p25_ja_multilang.py pick` wrote. Results go to
`OUT/runs/full/direct.<target>.json` (`whole.<target>.json` with `--whole`, which translates every
cue of the talk), the layout `scripts/p25_check.py` reads, and the cues that
failed every attempt to `OUT/runs/failures.json`. A target that has a file is not translated again.
Run it at a low priority and with one llama-server at a time (`P25_LLAMA_SERVER` may name a wrapper
that limits its threads).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

from backend.core import translate
from backend.core.languages import get
from backend.core.source_langs import JAPANESE_SOURCE
from backend.core.subtitle_io import render_subs, write_text_file
from backend.llm.ask import ChatFn
from scripts.p25_ja_multilang import sampled, serve, talk_cues

TALK = "full"


def run_targets(out: Path, chat: ChatFn, targets: list[str], *, whole: bool = False) -> None:
    cues = talk_cues(TALK)
    selected = {c.id for c in cues} if whole else sampled(out, TALK)[0]
    folder = out / "runs" / TALK
    folder.mkdir(parents=True, exist_ok=True)
    glossary = translate.glossary_for("ja", ())
    for code in targets:
        path = folder / f"{'whole' if whole else 'direct'}.{code}.json"
        if path.exists():
            continue
        failures: list[translate.Failure] = []
        staged = [replace(c, zh="" if c.id in selected else c.src) for c in cues]
        started = time.monotonic()
        result = translate.run(
            staged,
            chat,
            glossary,
            keep_english=True,
            lang=get(code),
            source=JAPANESE_SOURCE,
            on_failure=failures.append,
        )
        seconds = round(time.monotonic() - started, 1)
        kept = [replace(c, zh=c.zh if c.id in selected else "") for c in result]
        write_text_file(path, render_subs(kept))
        asked = sum(1 for c in kept if c.id in selected)
        report = out / "runs" / ("failures-whole.json" if whole else "failures.json")
        known: dict[str, object] = json.loads(report.read_text("utf-8")) if report.exists() else {}
        known[code] = {
            "cues": asked,
            "seconds": seconds,
            "failed": [f.cue_id for f in failures if f.cue_id in selected],
            "english": [f.cue_id for f in failures if f.english and f.cue_id in selected],
        }
        report.write_text(json.dumps(known, indent=1), encoding="utf-8")
        print(f"{code}: {asked} cues in {seconds} s, {len(failures)} failed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--targets", nargs="+", default=["en", "zh-CN", "ko"])
    parser.add_argument("--whole", action="store_true", help="translate every cue of the talk")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = cast("Path", args.out)
    serve(
        out,
        lambda chat: run_targets(out, chat, cast("list[str]", args.targets), whole=args.whole),
    )


if __name__ == "__main__":
    main()
