"""Z0 E3: the Chinese cue texts that the translation probe translates.

Run it in the scratch environment that holds the `opencc` wheel (not a repository dependency):

    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_units.py \\
        --fleurs-run q-auto --e5-run e5-q --converter s2t --fleurs-count 150

Two sets. `fleurs`: the recognised text of FLEURS Mandarin utterances (read speech), one cue per
utterance, spread evenly over the test split. `e5`: the cues of the app's own cue builder over the
minutes of the operator's video (`zh_z0_e5_asr.py`), which are talk-like and fast. Both are written
in Traditional characters with the chosen converter, the way Z1 will give them to the translator.
Output: `.work/zh-z0/runs/units.json` (derived from the video: stays under `.work`).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any, cast

from zh_z0_text import RUNS, WORK, load_utterances, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fleurs-run", required=True)
    parser.add_argument("--e5-run", required=True)
    parser.add_argument("--converter", default="s2t")
    parser.add_argument("--fleurs-count", type=int, default=150)
    args = parser.parse_args()
    opencc = cast("Any", importlib.import_module("opencc"))
    convert = opencc.OpenCC(args.converter).convert

    run = cast("dict[str, Any]", read_json(RUNS / f"{args.fleurs_run}.json"))
    texts = cast("dict[str, str]", run["texts"])
    keys = [u.key for u in load_utterances("zh") if u.key in texts and texts[u.key].strip()]
    step = max(1, len(keys) // args.fleurs_count)
    units: list[dict[str, Any]] = []
    for index, key in enumerate(keys[::step][: args.fleurs_count]):
        text = texts[key].strip()
        units.append(
            {
                "set": "fleurs",
                "id": index,
                "start": index * 20000,
                "end": index * 20000 + 15000,
                "orig": text,
                "text": convert(text),
            }
        )
    e5 = cast("dict[str, Any]", read_json(WORK / "e5" / f"{args.e5_run}.json"))
    for index, (start, end, text) in enumerate(cast("list[list[Any]]", e5["cues"])):
        units.append(
            {
                "set": "e5",
                "id": index,
                "start": int(start),
                "end": int(end),
                "orig": str(text),
                "text": convert(str(text)),
            }
        )
    write_json(RUNS / "units.json", {"converter": args.converter, "units": units})
    print(f"{len(units)} units written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
