"""P22 lever: ask Qwen3-8B whether a Japanese passage and the English passage after it say the same.

Pairs are a Japanese segment run (up to 3 segments) and the English run that follows it, from the
language map, and the same Japanese runs paired with an English run from the far side of the talk.

    uv run python scripts/p22_dup_judge.py LANGMAP.json OUT.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from backend.llm import client
from backend.llm.client import LlmConfig, Message
from backend.llm.local_server import NO_THINK, LlamaServer

MAIN = Path(__file__).resolve().parents[3]
SERVER = MAIN / "runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe"
GGUF = MAIN / "models/llm/Qwen3-8B-Q4_K_M.gguf"
SYSTEM = (
    "You compare a Japanese passage with an English passage from a talk. Both come from speech "
    "recognition and may contain errors. Decide whether the English passage says the same thing "
    'as the Japanese one, as an interpreter would. Reply with one JSON object: {"same": true} '
    'or {"same": false}.'
)
Rec = dict[str, Any]


def runs(rows: list[Rec]) -> list[tuple[str, str]]:
    """(Japanese run, the English run right after it) for every Japanese-then-English switch."""
    pairs: list[tuple[str, str]] = []
    k = 0
    while k < len(rows):
        if rows[k]["label"] != "ja":
            k += 1
            continue
        ja: list[str] = []
        while k < len(rows) and rows[k]["label"] == "ja":
            ja.append(rows[k]["text_qwen3"])
            k += 1
        en: list[str] = []
        while k < len(rows) and rows[k]["label"] == "en":
            en.append(rows[k]["text_qwen3"])
            k += 1
        if en and len("".join(ja)) > 25:
            pairs.append((" ".join(ja), " ".join(en)))
    return pairs


def ask(config: LlmConfig, ja: str, en: str) -> bool:
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": json.dumps({"japanese": ja, "english": en}, ensure_ascii=False),
        },
    ]
    reply = client.chat(config, messages, temperature=0.0, json_mode=True, max_tokens=None)
    return bool(cast("dict[str, Any]", json.loads(reply)).get("same"))


def main() -> None:
    rows = cast("list[Rec]", json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["segments"])
    pairs = runs(rows)
    far = [pairs[(k + len(pairs) // 2) % len(pairs)][1] for k in range(len(pairs))]
    log = Path(sys.argv[2]).with_suffix(".server.log")
    with LlamaServer(SERVER, GGUF, log_path=log, ctx=8192) as server:
        config = LlmConfig(server.base_url, "local", extra_body={**NO_THINK, "seed": 20261105})
        real = [ask(config, ja, en) for ja, en in pairs]
        shuffled = [ask(config, ja, f) for (ja, _), f in zip(pairs, far, strict=True)]
    summary = {
        "japanese_runs_followed_by_english": len(pairs),
        "judged_same_when_paired_with_next_english": sum(real),
        "judged_same_when_paired_with_unrelated_english": sum(shuffled),
        "examples": [
            {"ja": ja[:160], "en": en[:160], "same": r}
            for (ja, en), r in zip(pairs, real, strict=True)
        ][:6],
    }
    Path(sys.argv[2]).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "examples"}))


if __name__ == "__main__":
    main()
