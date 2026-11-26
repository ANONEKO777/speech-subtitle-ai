"""Z0 E3: translate Chinese cues into English and Japanese with the app's Qwen3-8B, and measure.

    uv run python scripts/zh_z0_translate.py run --variant standin --targets en ja
    uv run python scripts/zh_z0_translate.py run --variant draft --targets en ja
    uv run python scripts/zh_z0_translate.py report

`zh` is not a source of the app yet, so two stand-ins stand for its prompt (the output says which):

- `standin`: the prompts the app uses today, with Chinese text where they expect the other
  language. English output: the `en` route of the Japanese source (`ja_routes.ROUTES["en"]`). Japanese
  output: the English source's prompt with the `ja` target row, which is how English speech is
  translated into Japanese today (there is no Japanese-to-Japanese route).
- `draft`: a Chinese source prompt written for this probe (`ZH_RULES`), the same shape as
  `ja_routes.HOME_RULES` with the lines about kana, honorifics and Taiwan wording replaced. It is a
  sketch for Z1, not something the app has.

Length limits are off (`LOOSE`) so that the output length is what the model wants to write, and the
target language checks of the app stay on (no kana or Chinese characters in English; kana in
Japanese). `units.json` comes from `zh_z0_units.py`. Output: `.work/zh-z0/runs/tr-*.json`. One
llama-server at a time, Idle priority.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import replace
from types import MappingProxyType
from typing import Any, cast

from zh_z0_common import llama_server_files, set_idle_priority, wait_until_free
from zh_z0_text import RUNS, WORK, percentile, read_json, write_json

from backend.core import translate
from backend.core.ja_routes import ROUTES
from backend.core.languages import Density, Language, get
from backend.core.model import Cue
from backend.core.source_langs import (
    ENGLISH_SOURCE,
    JAPANESE_SOURCE,
    CueRules,
    OnFailure,
    SourceFiles,
    SourceLanguage,
    SourcePrompt,
)
from backend.llm.ask import json_chat
from backend.llm.client import LLM_SEED, LlmConfig
from backend.llm.local_server import NO_THINK, LlamaServer

LOOSE = Density(1000.0, 10_000, 0.0)
SENTENCE_END = re.compile(r"[。！？!?…][」』）)\"”]*\Z")
ZH_ENTRIES = (
    '{"id": 7, "zh": "[[7]]上個月，我做了一件有點[[8]]離譜的事。"} '
    'and {"id": 9, "zh": "我送出了 2,000 個 PR。"}'
)
ZH_RULES = """\
- Keep the speaker's spoken tone. Be natural and accurate. Do not add or remove information. Leave out spoken Chinese filler and padding such as "嗯", "呃", "那個", "這個", "就是" and "然後" when <<NAME>> does not need them<<FILLER_NOT>>. Leave fillers out only from the cue they are in, and never move words between cues. A cue that holds only a filler gets <<FILLER_CUE>>.
- Chinese often leaves the subject out. Read the context to find who or what each sentence is about, and write that subject only when <<NAME>> needs it. Never invent a subject, a person or a number that the sentence and its context do not give.
- A name written in Chinese characters is a product, company, work, character or place. Write it the way <<NAME>> readers know it, in Latin letters when it has a Latin spelling, and never turn it into a guessed sound-alike. The speech recognition garbles names, so take the name the context gives, not a literal copy of the garbled sound.
- A Latin word the speaker says inside a Chinese sentence stays in Latin letters.
- Use the same translation for a name or term everywhere.
- Translate only what the Chinese says. Never add a reason, a link such as "therefore", a clause or a name that the sentence does not have, and never turn a plain statement into an explanation.
- Keep every number exactly as spoken: the same digits, the decimal point and the percent sign, and never drop one.
- The Chinese comes from speech recognition and may contain mishearings. Use the context to pick the most likely meaning."""
ZH_LEFTOVER = {
    "en": "- Translate every Chinese word except names, product names and technical terms that are normally written in Latin letters. Do not leave Chinese characters in the <<NAME>>.",
    "ja": "- Translate every Chinese word except names, product names and technical terms that are normally written in Latin letters. Write Japanese, with Japanese kanji forms (国, 学, 会) and kana, and never copy the Chinese sentence.",
}
EXAMPLES = {
    "en": '{"translations": [{"id": 7, "text": "[[7]]Last month, I did something a bit [[8]]outrageous."}, {"id": 9, "text": "I shipped 2,000 PRs."}]}',
    "ja": '{"translations": [{"id": 7, "text": "[[7]]先月、ちょっと[[8]]とんでもないことをやりました。"}, {"id": 9, "text": "PRを2,000件出しました。"}]}',
}
KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
HAN = re.compile("[㐀-鿿]")


def _none(text: str) -> str | None:
    return None


def _same(text: str) -> str:
    return text


def zh_draft(target: str) -> SourceLanguage:
    prompt = SourcePrompt(
        "Chinese", "zh", ZH_ENTRIES, ZH_RULES, ZH_LEFTOVER[target], {target: EXAMPLES[target]}
    )
    return replace(
        JAPANESE_SOURCE,
        code="zh",
        name="Chinese",
        native="中文",
        prompt=prompt,
        files=SourceFiles("subs.zh.json", "zh.srt"),
        sentence_end=SENTENCE_END,
        sentence_continues=None,
        density=LOOSE,
        targets=None,
        routes=MappingProxyType({}),
        problem=_none,
        clean=_same,
        mends_glossary=False,
        repair=None,
        rejects_bare_punctuation=False,
        terms=(),
        fix_from_source=None,
        needs_script=None,
        on_failure=OnFailure.LEAVE_EMPTY,
    )


def standin(target: str) -> SourceLanguage:
    if target == "en":
        route = replace(ROUTES["en"], density=LOOSE)
        return replace(JAPANESE_SOURCE, routes=MappingProxyType({"en": route}))
    return replace(
        ENGLISH_SOURCE,
        code="zh",
        cues=CueRules(max_line_chars=40, unspaced=True, max_cps=14.0),
        sentence_end=SENTENCE_END,
        density=LOOSE,
        on_failure=OnFailure.LEAVE_EMPTY,
    )


def source_for(variant: str, target: str) -> SourceLanguage:
    return zh_draft(target) if variant == "draft" else standin(target)


def stats(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p99": percentile(values, 99),
        "max": max(values, default=0.0),
        "mean": sum(values) / max(len(values), 1),
    }


def run(variant: str, targets: list[str], sets: list[str], limit: int | None) -> None:
    set_idle_priority()
    wait_until_free()
    data = cast("dict[str, Any]", read_json(RUNS / "units.json"))
    units = cast("list[dict[str, Any]]", data["units"])
    exe, gguf = llama_server_files()
    log = WORK / "tmp" / f"llama-{variant}.log"
    with LlamaServer(exe, gguf, log_path=log, ctx=8192) as server:
        config = LlmConfig(server.base_url, "local", extra_body={**NO_THINK, "seed": LLM_SEED})
        chat = json_chat(config)
        for set_name in sets:
            rows = [u for u in units if u["set"] == set_name][:limit]
            cues = [
                Cue(i, int(u["start"]), int(u["end"]), str(u["text"]), lang="zh")
                for i, u in enumerate(rows)
            ]
            for target in targets:
                lang: Language = get(target)
                source = source_for(variant, target)
                failed: list[int] = []
                started = time.monotonic()
                glossary = translate.glossary_for("zh", ())
                result = translate.run(
                    cues,
                    chat,
                    glossary,
                    keep_english=True,
                    lang=lang,
                    source=source,
                    on_failure=lambda f, sink=failed: sink.append(f.cue_id),
                )
                seconds = time.monotonic() - started
                out: list[dict[str, Any]] = []
                for cue in result:
                    src = cue.src
                    out.append(
                        {"id": cue.id, "src": src, "zh": cue.zh, "orig": rows[cue.id]["orig"]}
                    )
                write_json(
                    RUNS / f"tr-{variant}-{set_name}-{target}.json",
                    {"variant": variant, "set": set_name, "target": target, "seconds": seconds,
                     "failed": failed, "rows": out},
                )  # fmt: skip
                print(
                    f"{variant} {set_name} -> {target}: {len(out)} cues, {len(failed)} failed, {seconds:.0f} s",
                    flush=True,
                )


def report() -> None:
    print(
        "| variant | set | target | cues | empty | chars per source char p50 / p90 / p99 | words per source char p90 | kana in en | han in en | ja without kana |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for path in sorted(RUNS.glob("tr-*.json")):
        d = cast("dict[str, Any]", read_json(path))
        rows = cast("list[dict[str, Any]]", d["rows"])
        done = [r for r in rows if r["zh"]]
        ratio = [len(r["zh"]) / max(len(r["src"]), 1) for r in done]
        words = [len(r["zh"].split()) / max(len(r["src"]), 1) for r in done]
        kana = sum(1 for r in done if KANA.search(r["zh"])) if d["target"] == "en" else 0
        han = sum(1 for r in done if HAN.search(r["zh"])) if d["target"] == "en" else 0
        no_kana = (
            sum(1 for r in done if len(HAN.findall(r["src"])) >= 5 and not KANA.search(r["zh"]))
            if d["target"] == "ja"
            else 0
        )
        s = stats(ratio)
        print(
            f"| {d['variant']} | {d['set']} | {d['target']} | {len(rows)} | {len(rows) - len(done)} | "
            f"{s['p50']:.2f} / {s['p90']:.2f} / {s['p99']:.2f} | {stats(words)['p90']:.2f} | {kana} | {han} | {no_kana} |"
        )


def samples() -> None:
    """20 cues picked by position, not by quality: every 8th of the FLEURS set (14) and every 20th of
    the anime ASR cues (6, cut to their first 12 characters and 12 words of translation, because
    that video is not ours to quote). FLEURS is CC BY 4.0, so its sentences are quoted whole."""
    picks = [("fleurs", i) for i in range(0, 112, 8)] + [("e5", i) for i in range(0, 120, 20)]
    print("| set | source | English | Japanese | EN per char | JA per char |")
    print("|---|---|---|---|---|---|")
    for set_name, index in picks:
        en = cast("list[dict[str, Any]]", read_json(RUNS / f"tr-draft-{set_name}-en.json")["rows"])[
            index
        ]
        ja = cast("list[dict[str, Any]]", read_json(RUNS / f"tr-draft-{set_name}-ja.json")["rows"])[
            index
        ]
        src = str(en["src"]).replace("\n", "")
        out_en, out_ja = str(en["zh"]), str(ja["zh"])
        shown = (src, out_en, out_ja)
        if set_name == "e5":
            shown = (src[:12] + "…", " ".join(out_en.split()[:12]) + " …", out_ja[:14] + "…")
        print(
            f"| {set_name} {index} | {shown[0]} | {shown[1]} | {shown[2]} | "
            f"{len(out_en) / max(len(src), 1):.2f} | {len(out_ja) / max(len(src), 1):.2f} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--variant", choices=("standin", "draft"), required=True)
    runner.add_argument("--targets", nargs="+", default=["en", "ja"])
    runner.add_argument("--sets", nargs="+", default=["fleurs", "e5", "ref"])
    runner.add_argument("--limit", type=int)
    sub.add_parser("report")
    sub.add_parser("samples")
    args = parser.parse_args()
    if args.cmd == "run":
        run(args.variant, args.targets, args.sets, args.limit)
    elif args.cmd == "samples":
        samples()
    else:
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
