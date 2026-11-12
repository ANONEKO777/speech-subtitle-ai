"""P23b lever: turn a candidate's output into the tag file `p23b_score.py` reads.

`words WORDS.json`: a word list from `p23b_proto.py` (every word has a `lang`). A manifest segment
gets the languages of the words whose middle lies inside it: `ja`, `en`, both, or none.
`whisper AUTO.json JA.json`: Whisper `-l auto` per chunk (candidate Y). The tag is the language
Whisper detected when it is `ja` or `en`. For any other detected language (Korean and Chinese
come back for short pieces) the chunk is taken from the `-l ja` run, tagged `ja`.

    uv run python scripts/p23b_tags.py MANIFEST.json OUT.json words WORDS.json
    uv run python scripts/p23b_tags.py MANIFEST.json OUT.json whisper AUTO.json JA.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast


def load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def tags_from_words(manifest: dict[str, Any], words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in manifest["segments"]:
        lo, hi = seg["start_s"] * 1000, seg["end_s"] * 1000
        langs = sorted(
            {w["lang"] for w in words if lo <= (w["start_ms"] + w["end_ms"]) / 2 <= hi if w["lang"]}
        )
        out.append({"id": seg["id"], "tag": langs})
    return out


def tags_from_whisper(
    manifest: dict[str, Any], auto: dict[str, Any], ja: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in manifest["segments"]:
        index = int(seg["id"][1:])
        chunk = cast("dict[str, Any]", auto["chunks"][index])
        lid = chunk.get("detected")
        text = "".join(s["text"] for s in ja["chunks"][index]["segments"]).strip()
        tag = lid if lid in ("ja", "en") else ("ja" if text else "none")
        out.append({"id": seg["id"], "tag": tag, "detected": lid})
    return out


def main() -> None:
    manifest = load(sys.argv[1])
    if sys.argv[3] == "words":
        rows = tags_from_words(manifest, load(sys.argv[4]))
    else:
        rows = tags_from_whisper(manifest, load(sys.argv[4]), load(sys.argv[5]))
    Path(sys.argv[2]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
