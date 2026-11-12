"""P23b lever: character error rates for a candidate's words (`p23b_proto.py` output).

`ja REF.json WORDS.json`: the Japanese CER on the three Kirby windows of
`docs/p22/reference-kirby.json` (Japanese characters only, as P22 counted). The reference is one model's reading of three engines'
text, not a person's, and it sits closer to Whisper than to Qwen3 (P22 section 8).

`en WORDS.json WHISPER_EN.json CHUNKS.json [MANIFEST.json LABELS.json]`: the English disagreement
rate. No person wrote the English, so the reference is Whisper `-l en` on the same chunk, a forced
decode of a different engine. The number is how far the candidate is from that proxy, not an error
rate. It covers chunks of 2 s or longer whose words are all English; with a manifest and labels it
covers only the segments a person heard as English.

    uv run python scripts/p23b_cer.py ja REF WORDS
    uv run python scripts/p23b_cer.py en WORDS WHISPER_EN CHUNKS [MANIFEST LABELS]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from p22_analyze import edit_distance, load, normalise

PAD_MS = 3000
MIN_EN_MS = 2000


def rows(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def japanese(ref_path: str, words_path: str) -> None:
    ref = rows(ref_path)["kirby"]
    words = cast("list[dict[str, Any]]", rows(words_path))
    errors = total = 0
    per: list[str] = []
    for w in ref:
        lo, hi = w["start_s"] * 1000 - PAD_MS, w["end_s"] * 1000 + PAD_MS
        said = "".join(x["text"] for x in words if lo <= x["start_ms"] < hi)
        r = normalise(w["text"], for_cer=True, ja_only=True)
        h = normalise(said, for_cer=True, ja_only=True)
        e = edit_distance(r, h, free_hyp_edges=True)
        errors, total = errors + e, total + len(r)
        per.append(f"{e / max(1, len(r)):.3f}")
    print(f"Japanese CER {errors / total:.4f} ({errors}/{total} chars, {len(ref)} windows) {per}")


def english(argv: list[str]) -> None:
    words = cast("list[dict[str, Any]]", rows(argv[0]))
    whisper = load(Path(argv[1]))
    chunks = cast("list[list[int]]", rows(argv[2]))
    keep: set[int] | None = None
    if len(argv) > 4:
        labels = {r["id"]: r["label"] for r in rows(argv[4])["labels"]}
        keep = {int(i[1:]) for i, label in labels.items() if label == "en"}
    errors = total = used = 0
    for index, (lo, hi) in enumerate(chunks):
        if hi - lo < MIN_EN_MS or (keep is not None and index not in keep):
            continue
        inside = [x for x in words if lo <= (x["start_ms"] + x["end_ms"]) / 2 <= hi]
        if not inside or any(x["lang"] != "en" for x in inside):
            continue
        ref = normalise(" ".join(s.text for s in whisper.segs if s.chunk == index), for_cer=True)
        hyp = normalise(" ".join(x["text"] for x in inside), for_cer=True)
        if not ref:
            continue
        errors, total, used = errors + edit_distance(ref, hyp), total + len(ref), used + 1
    rate = errors / total
    print(
        f"English disagreement with Whisper -l en: {rate:.4f} ({errors}/{total} chars, {used} chunks)"
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if sys.argv[1] == "ja":
        japanese(sys.argv[2], sys.argv[3])
    else:
        english(sys.argv[2:])
