"""P22 lever: translate probe sentences with the project's Qwen3-8B and the project's own checks.

Each batch of up to 10 sentences goes to a local llama-server exactly as `translate.py` builds a
request (same system prompt, same JSON body, JSON mode, temperature 0, same seed). Two prompts run
on the same sentences. `current` is the shipped prompt with the source text in its "en" field.
`candidate` swaps in the source-language wording that the P22 decision proposes.

    uv run python scripts/p22_translate_probe.py SENTENCES.json OUT.json
SENTENCES.json is a list of {"id", "video", "lang", "src"}; lang is ja or en.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, cast

from backend.core import translate
from backend.core.languages import get as get_language
from backend.core.zh_tw import in_big5
from backend.llm import client
from backend.llm.client import LlmConfig, Message
from backend.llm.local_server import NO_THINK, LlamaServer

MAIN = Path(__file__).resolve().parents[3]
SERVER = MAIN / "runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe"
GGUF = MAIN / "models/llm/Qwen3-8B-Q4_K_M.gguf"
SEED = 20261105
KANA = re.compile("[぀-ゟ゠-ヿｦ-ﾟ]")
CJK = re.compile("[㐀-鿿]")

CANDIDATE_RULES = (
    Path(__file__).resolve().parent.parent / "docs/p22/candidate-rules.md"
).read_text(encoding="utf-8")


def candidate_prompt(base: str) -> str:
    text = base.replace("Translate English subtitles", "Translate Japanese and English subtitles")
    text = text.replace(
        '{"id": number, "en": "English text"}', '{"id": number, "lang": "ja or en", "src": "text"}'
    )
    text = text.replace('"en": "[[7]]', '"src": "[[7]]').replace(
        '{"id": 9, "en"', '{"id": 9, "src"'
    )
    text = text.replace(
        "Rules for the translation:\n", "Rules for the translation:\n" + CANDIDATE_RULES + "\n"
    )
    text = text.replace(
        "The English comes from speech recognition", "The source comes from speech recognition"
    )
    return text.replace("Translate every English word except", "Translate every word except")


def request(system: str, rows: list[dict[str, Any]], key: str, with_lang: bool) -> list[Message]:
    body = {
        "context_before": "",
        "context_after": "",
        "translate": [
            {"id": r["id"], **({"lang": r["lang"]} if with_lang else {}), key: r["src"]}
            for r in rows
        ],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(body, ensure_ascii=False)},
    ]


def run_variant(
    config: LlmConfig, system: str, rows: list[dict[str, Any]], key: str, with_lang: bool
) -> dict[int, str]:
    out: dict[int, str] = {}
    for i in range(0, len(rows), 10):
        batch = rows[i : i + 10]
        reply = client.chat(
            config,
            request(system, batch, key, with_lang),
            temperature=0.0,
            json_mode=True,
            max_tokens=None,
        )
        try:
            doc = cast("dict[str, Any]", json.loads(reply))
            for item in cast("list[dict[str, Any]]", doc["translations"]):
                out[int(item["id"])] = str(item.get("zh") or item.get("text") or "")
        except (ValueError, KeyError, TypeError):
            for r in batch:
                out.setdefault(r["id"], f"<unparsed reply: {reply[:80]}>")
    return out


def checks(zh: str, src: str) -> list[str]:
    lang = get_language("zh-TW")
    found: list[str] = []
    if problem := lang.problem(zh, src):
        found.append(f"project: {problem}")
    if KANA.search(zh):
        found.append("kana left")
    odd = sorted({c for c in zh if CJK.search(c) and not in_big5(c)})
    if odd:
        found.append("non-Big5 kanji " + "".join(odd))
    return found


def main() -> int:
    sentences = cast(
        "list[dict[str, Any]]", json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    )
    base = translate.system_prompt_template(get_language("zh-TW")).replace(
        translate.GLOSSARY_MARK, ""
    )
    variants = {
        "current": (base.rstrip() + "\n", "en", False),
        "candidate": (candidate_prompt(base).rstrip() + "\n", "src", True),
    }
    results: dict[str, dict[int, str]] = {}
    log = Path(sys.argv[2]).with_suffix(".server.log")
    with LlamaServer(SERVER, GGUF, log_path=log, ctx=8192) as server:
        config = LlmConfig(server.base_url, "local", extra_body={**NO_THINK, "seed": SEED})
        for name, (system, key, with_lang) in variants.items():
            started = time.monotonic()
            results[name] = run_variant(config, system, sentences, key, with_lang)
            print(f"{name}: {time.monotonic() - started:.1f}s", flush=True)
    rows: list[dict[str, Any]] = []
    for s in sentences:
        row: dict[str, Any] = dict(s)
        for name in variants:
            zh = results[name].get(s["id"], "")
            row[name] = zh
            row[f"{name}_checks"] = checks(zh, s["src"])
        rows.append(row)
    Path(sys.argv[2]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
