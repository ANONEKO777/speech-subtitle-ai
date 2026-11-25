"""Z0 E3: how many Qwen3 tokens a Chinese character costs, for `chars_per_token` of a `zh` source.

    uv run python scripts/zh_z0_tokens.py

It starts the app llama-server (Qwen3-8B) and asks its `/tokenize` for the source texts of
`units.json` (FLEURS recognised text, the anime cues, the hard-sub lines) and of the English and
Japanese translations `zh_z0_translate.py` wrote, and prints characters per token. The Japanese
source row has 1.2 characters per token; a Han character is the unit that matters here.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any, cast

from zh_z0_common import llama_server_files, set_idle_priority, wait_until_free
from zh_z0_text import RUNS, WORK, is_han, read_json

from backend.llm.local_server import LlamaServer


def count_tokens(base: str, text: str) -> int:
    request = urllib.request.Request(  # noqa: S310
        base.removesuffix("/v1") + "/tokenize",
        data=json.dumps({"content": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as reply:  # noqa: S310
        return len(cast("dict[str, Any]", json.loads(reply.read()))["tokens"])


def main() -> int:
    set_idle_priority()
    wait_until_free()
    units = cast("list[dict[str, Any]]", read_json(RUNS / "units.json")["units"])
    groups: dict[str, list[str]] = {}
    for u in units:
        groups.setdefault(f"source {u['set']}", []).append(str(u["text"]))
    for path in sorted(RUNS.glob("tr-draft-*.json")):
        rows = cast("list[dict[str, Any]]", read_json(path)["rows"])
        groups[f"output {path.stem.removeprefix('tr-draft-')}"] = [
            str(r["zh"]) for r in rows if r["zh"]
        ]
    exe, gguf = llama_server_files()
    with LlamaServer(exe, gguf, log_path=WORK / "tmp" / "llama-tokens.log", ctx=8192) as server:
        for name, texts in groups.items():
            chars = sum(len(t) for t in texts)
            han = sum(1 for t in texts for c in t if is_han(c))
            tokens = sum(count_tokens(server.base_url, t) for t in texts)
            print(
                f"{name}: {len(texts)} texts, {chars} characters ({han} Han), {tokens} tokens, "
                f"{chars / tokens:.2f} characters per token, {han / tokens:.2f} Han per token"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
