"""P25 lever: translate a Japanese talk into the 12 other target languages by three routes.

    python scripts/p25_ja_multilang.py pick OUT              # choose the sentence units, once
    python scripts/p25_ja_multilang.py run OUT [--targets ko th] [--routes direct via-en via-zh]
    python scripts/p25_ja_multilang.py back OUT              # back-translate a sample into Japanese

OUT is the evidence folder. `pick` writes OUT/units.json (the cue ids of the sampled sentence units
of each talk, fixed seed). `run` starts the local Qwen3-8B on a free port (stopped on exit) and
writes one cue file per route and target under OUT/runs/<talk>/, plus OUT/runs/timing.jsonl:

- `direct`: Japanese to the target in one step.
- `via-en`: Japanese to English over the whole talk, then English to the target for the sampled
  sentences, with the real English cues around them as context.
- `via-zh`: the same with the current Traditional Chinese (Taiwan) output as the middle step.

It calls `translate.run` and the prompt builders of the pipeline. What it changes, because the
Japanese source is gated to zh-TW in the registry (`SourceLanguage.targets`) and its rules and
checks are written for Chinese: (1) the Japanese rules lose the Traditional-kanji and Taiwan-wording
lines and say "the target language" in place of Chinese; (2) the source's own clean-up, term table
and rewrites for Taiwan Chinese are off; (3) the length check of `_check_text` is off (the density
is a limit of 1000 times), because its 1.1 times the Japanese length cannot hold a Latin-script
language; `p25_check.py` reports the real ratios instead; (4) the script check of the target stays,
but `needs_script` counts English words in the Japanese, so a Latin-script reply left in English
passes it (the checker looks at every output for that). `back` is not part of the pipeline.
`via-zh` and the direct zh-TW run use the unchanged zh-TW flow of this checkout.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

from backend.core import translate
from backend.core.language_prompts import Prompt
from backend.core.languages import LANGUAGES, Density, Language, get
from backend.core.model import Cue
from backend.core.source_langs import (
    ENGLISH_SOURCE,
    JAPANESE_SOURCE,
    MIXED_SOURCE,
    SourceFiles,
    SourceLanguage,
    SourcePrompt,
)
from backend.core.subtitle_io import parse_subs, read_text_file, render_subs, write_text_file
from backend.llm.ask import ChatFn, ReplyError, ask, json_chat, parse_json_reply
from backend.llm.client import LLM_SEED, LlmConfig, Message
from backend.llm.local_server import NO_THINK, LlamaServer

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path("D:/WebProject/speech-subtitle-ai")
SERVER = "runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe"
SERVER_ENV = "P25_LLAMA_SERVER"
"""A path in this variable replaces the server program, for a wrapper that adds `-t 2`."""
MODEL = "models/llm/Qwen3-8B-Q4_K_M.gguf"

TALKS: dict[str, tuple[Path, str]] = {
    "full": (ASSETS / ".work/p23a/full/proj/subs.ja.json", "ja"),
    "mixed": (ASSETS / ".work/p23b/kirby.vst/subs.src.json", "ja+en"),
}
UNITS_PER_TALK = {"full": 40, "mixed": 10}
BACK_PER_TALK = {"full": 24, "mixed": 6}
MIN_UNIT_CHARS = 12
SEED = 2511
TARGETS = ("en", "zh-CN", "ko", "es", "fr", "de", "pt", "it", "ru", "vi", "th", "id")
ROUTES = ("direct", "via-en", "via-zh")
LOOSE = Density(1000.0, 10_000, 0.0)
_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")

log = logging.getLogger("p25")


def _no_problem(text: str) -> str | None:
    return None


def _identity(text: str) -> str:
    return text


def _no_kana(text: str) -> str | None:
    if kana := sorted(set(_KANA.findall(text))):
        return f"still holds Japanese kana {''.join(kana)}; translate it"
    return None


_REWRITES = (
    (
        "and is spelled in Chinese characters when it has no Latin spelling",
        "and is written the way <<NAME>> readers usually write it when it has no Latin spelling",
    ),
    ("when Taiwan has a common word for it", "when <<NAME>> has a common word for it"),
    (
        "a link such as 為了解決這個問題 or 因此, a clause",
        'a linking phrase such as "to solve this problem" or "therefore", a clause',
    ),
)
_DROPPED = ("- Write every Japanese kanji", "- Use Taiwan wording")
_NEVER_KANA = (
    "- Never leave Japanese kana in the translation. Write the name of a Japanese person or place "
    "the usual way <<NAME>> does."
)


def generic_rules(rules: str) -> str:
    """The Japanese rules of the pipeline without the lines about Taiwan Chinese."""
    text = "\n".join(line for line in rules.split("\n") if not line.startswith(_DROPPED))
    for old, new in _REWRITES:
        if old not in text:
            raise ValueError(f"the Japanese rules no longer hold {old!r}")
        text = text.replace(old, new)
    return f"{text}\n{_NEVER_KANA}"


def _generic(source: SourceLanguage) -> SourceLanguage:
    base = source.prompt
    prompt = SourcePrompt(
        base.name, base.key, base.entries, generic_rules(base.rules), base.leftover, {}
    )
    return replace(
        source,
        prompt=prompt,
        density=LOOSE,
        targets=None,
        problem=_no_kana,
        clean=_identity,
        fix_from_source=None,
        terms=(),
    )


GENERIC_JA = _generic(JAPANESE_SOURCE)
GENERIC_MIXED = replace(_generic(MIXED_SOURCE), members=(GENERIC_JA, ENGLISH_SOURCE))

_ZH_RULES = (
    "- Keep the speaker's spoken tone. Be natural and accurate. Do not add or remove information. "
    "Leave out spoken filler words<<FILLER_NOT>>. Leave fillers out only from the cue they are in, "
    "and never move words between cues. A cue that holds only a filler gets <<FILLER_CUE>>.\n"
    "- Keep product names, company names, people's names, code, file names and commands in their "
    "original spelling. A well-known person or place may be written in <<NAME>>.\n"
    "- The Chinese is itself a translation of Japanese speech and may contain errors. Use the "
    "context to pick the most likely meaning."
)
ZH_SOURCE = replace(
    JAPANESE_SOURCE,
    code="zh-TW",
    name="Traditional Chinese",
    native="繁體中文",
    prompt=SourcePrompt(
        "Traditional Chinese",
        "zh",
        '{"id": 7, "zh": "[[7]]上個月，我做了一件有點[[8]]離譜的事。"} '
        'and {"id": 9, "zh": "我送出了 2,000 個 PR。"}',
        _ZH_RULES,
        "- Translate every Chinese word except names, product names and technical terms that are "
        "normally written in Latin letters. Do not leave Chinese characters in the <<NAME>>.",
        {},
    ),
    files=SourceFiles("subs.zh-TW.json", "zh-TW.srt"),
    sentence_end=re.compile(r"[。！？!?…][」』）)\"”]*\Z"),
    sentence_continues=None,
    density=LOOSE,
    targets=None,
    problem=_no_problem,
    clean=_identity,
    mends_glossary=False,
    repair=None,
    rejects_bare_punctuation=False,
    terms=(),
    fix_from_source=None,
)

_FOREIGN = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ㐀-䶿一-鿿豈-﫿가-힯฀-๿Ѐ-ӿ]")


def _check_english(text: str, en: str, required: bool) -> str | None:
    if _FOREIGN.search(text):
        return "contains Japanese, Chinese, Korean, Thai or Cyrillic characters; write English"
    return None


def english_target() -> Language:
    """English as a target: the registry has no entry for it, as English is only a source there."""
    example = (
        '{"translations": [{"id": 7, "text": "[[7]]So last month, I did something pretty '
        '[[8]]crazy."}, {"id": 9, "text": "I shipped 2,000 PRs."}]}'
    )
    prompt = Prompt(
        target="English",
        name="English",
        reply_name="English",
        key="text",
        example=example,
        style="- Write natural, spoken English. Address the audience in one consistent form.\n",
        filler_not=", and never write a filler sound in their place",
        you_know=", or written with a short natural equivalent",
        filler_cue="Um, ",
    )
    return replace(
        LANGUAGES["es"],
        code="en",
        name="English",
        native="English",
        file_code="en",
        prompt=prompt,
        check=_check_english,
        density=LOOSE,
    )


def target(code: str) -> Language:
    return english_target() if code == "en" else get(code)


def _load(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def talk_cues(talk: str) -> list[Cue]:
    return parse_subs(read_text_file(TALKS[talk][0]))


def talk_source(talk: str) -> SourceLanguage:
    return MIXED_SOURCE if TALKS[talk][1] == "ja+en" else JAPANESE_SOURCE


def flat_ja(cues: Sequence[Cue], ids: Iterable[int]) -> str:
    wanted = set(ids)
    return "".join(c.src.replace("\n", "") for c in cues if c.id in wanted)


def pick(out: Path) -> None:
    """Sample sentence units spread over each talk: one at random from each of N equal slices of
    the units that are Japanese and long enough to be worth a back-translation."""
    rng = random.Random(SEED)
    chosen: dict[str, list[dict[str, object]]] = {}
    for talk, count in UNITS_PER_TALK.items():
        cues = talk_cues(talk)
        units = [
            u
            for u in translate.sentence_units(
                cues, 0, len(cues), translate.MAX_UNIT_CUES, talk_source(talk)
            )
            if all(c.lang == "ja" for c in cues[u.start : u.stop])
            and len(flat_ja(cues, [c.id for c in cues[u.start : u.stop]])) >= MIN_UNIT_CHARS
        ]
        edges = [round(i * len(units) / count) for i in range(count + 1)]
        rows = [units[rng.randrange(edges[i], edges[i + 1])] for i in range(count)]
        back = set(rng.sample(range(count), BACK_PER_TALK[talk]))
        chosen[talk] = [
            {"ids": [c.id for c in cues[u.start : u.stop]], "back": i in back}
            for i, u in enumerate(rows)
        ]
    out.mkdir(parents=True, exist_ok=True)
    (out / "units.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    lines = [f"seed {SEED}"]
    for talk, rows in chosen.items():
        lines.append(
            f"{talk}: " + "; ".join(",".join(map(str, cast("list[int]", r["ids"]))) for r in rows)
        )
    (out / "unit-ids.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def sampled(out: Path, talk: str) -> tuple[set[int], list[list[int]], set[int]]:
    """The sampled cue ids, the units, and the ids of the units chosen for back-translation."""
    rows = cast("list[dict[str, object]]", _load(out / "units.json")[talk])
    units = [cast("list[int]", r["ids"]) for r in rows]
    back = {u[0] for u, r in zip(units, rows, strict=True) if r["back"]}
    return {i for u in units for i in u}, units, back


def translate_cues(
    chat: ChatFn,
    cues: Sequence[Cue],
    selected: set[int],
    *,
    lang: Language,
    source: SourceLanguage,
    glossary: Sequence[translate.GlossaryEntry],
) -> list[Cue]:
    """Translate only `selected`; the others stay as untranslated context with their real text."""
    staged = [replace(c, zh="" if c.id in selected else c.src) for c in cues]
    result = translate.run(staged, chat, glossary, keep_english=True, lang=lang, source=source)
    return [replace(c, zh=c.zh if c.id in selected else "") for c in result]


def pivot_cues(cues: Sequence[Cue], middle: Sequence[Cue], code: str) -> list[Cue]:
    """The Japanese cues with their middle-language text as the source, ready to translate on."""
    said = {c.id: c.zh for c in middle}
    return [replace(c, src=said.get(c.id) or "…", zh="", lang=code) for c in cues if c.lang == "ja"]


def keep_only(glossary: Sequence[translate.GlossaryEntry]) -> list[translate.GlossaryEntry]:
    """The names that stay as written: a Japanese-term entry makes no sense in a pivot step."""
    return [e for e in glossary if not e.zh]


def restrict(cues: Sequence[Cue], selected: set[int]) -> list[Cue]:
    return [replace(c, zh=c.zh if c.id in selected else "") for c in cues]


class Runner:
    def __init__(self, out: Path, chat: ChatFn) -> None:
        self.out, self.chat = out, chat

    def cached(self, path: Path, make: Callable[[], list[Cue]], label: str) -> list[Cue]:
        if path.exists():
            return parse_subs(read_text_file(path))
        started = time.monotonic()
        cues = make()
        seconds = round(time.monotonic() - started, 1)
        write_text_file(path, render_subs(cues))
        asked = sum(1 for c in cues if c.zh)
        with (self.out / "runs/timing.jsonl").open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"run": label, "cues": asked, "seconds": seconds}) + "\n")
        print(f"{label}: {asked} cues in {seconds} s", flush=True)
        return cues

    def talk(self, talk: str, targets: Sequence[str], routes: Sequence[str]) -> None:
        folder = self.out / "runs" / talk
        folder.mkdir(parents=True, exist_ok=True)
        cues = talk_cues(talk)
        code = TALKS[talk][1]
        source = talk_source(talk)
        generic = GENERIC_MIXED if source.mixed else GENERIC_JA
        everything = {c.id for c in cues if c.lang == "ja"}
        selected, _, _ = sampled(self.out, talk)
        names = translate.glossary_for(code, ())
        english = self.cached(
            folder / "ja-en.full.json",
            lambda: translate_cues(
                self.chat, cues, everything, lang=english_target(), source=generic, glossary=names
            ),
            f"{talk}/ja-en.full",
        )
        write_text_file(folder / "direct.en.json", render_subs(restrict(english, selected)))
        steps = {
            "direct": (cues, generic, names),
            "via-en": (pivot_cues(cues, english, "en"), ENGLISH_SOURCE, keep_only(names)),
        }
        if "via-zh" in routes:
            zh = self.cached(
                folder / "ja-zh-TW.full.json",
                lambda: translate_cues(
                    self.chat,
                    cues,
                    everything,
                    lang=translate.DEFAULT,
                    source=source,
                    glossary=names,
                ),
                f"{talk}/ja-zh-TW.full",
            )
            write_text_file(folder / "direct.zh-TW.json", render_subs(restrict(zh, selected)))
            steps["via-zh"] = (pivot_cues(cues, zh, "zh-TW"), ZH_SOURCE, keep_only(names))
        for route in routes:
            start, step_source, step_names = steps[route]
            for code_to in targets:
                if code_to == "en" and route != "via-zh":
                    continue
                self.cached(
                    folder / f"{route}.{code_to}.json",
                    lambda c=code_to, a=start, b=step_source, n=step_names: translate_cues(
                        self.chat,
                        a,
                        selected,
                        lang=target(c),
                        source=b,
                        glossary=n,
                    ),
                    f"{talk}/{route}.{code_to}",
                )


BACK_BATCH = 5
_BACK_SYSTEM = (
    'You translate subtitles from {name} into Japanese. You receive one JSON object {{"translate": '
    '[{{"id": n, "text": "..."}}]}}. Reply with one JSON object and nothing else: '
    '{{"translations": [{{"id": n, "ja": "the Japanese translation"}}]}}. One entry per input '
    "entry, same ids. Translate faithfully and completely. Do not add, explain or omit anything."
)
_JUDGE_SYSTEM = (
    'You compare two Japanese sentences. You receive one JSON object {"pairs": [{"id": n, '
    '"original": "...", "other": "..."}]}. Score how well "other" keeps the meaning of "original" '
    "from 0 to 5: 5 same meaning, 4 small loss, 3 main point kept but a detail wrong or missing, "
    "2 partly the same, 1 mostly different, 0 unrelated or opposite. Judge meaning, not wording. "
    'Reply with one JSON object and nothing else: {"scores": [{"id": n, "score": 4}]}.'
)


def _by_id(text: str, wanted: Sequence[int], key: str, kind: type) -> dict[int, object]:
    doc = parse_json_reply(text)
    items = (
        cast("dict[str, object]", doc).get("translations" if key == "ja" else "scores")
        if isinstance(doc, dict)
        else doc
    )
    if not isinstance(items, list):
        raise ReplyError("the reply must be a JSON object with a list")
    found: dict[int, object] = {}
    for item in cast("list[object]", items):
        row = cast("dict[str, object]", item) if isinstance(item, dict) else {}
        if type(row.get("id")) is int and isinstance(row.get(key), kind):
            found[cast("int", row["id"])] = row[key]
    if missing := [i for i in wanted if i not in found]:
        raise ReplyError(f"missing ids {missing}")
    return found


def _ask_all(
    chat: ChatFn,
    system: str,
    body_key: str,
    rows: Sequence[dict[str, object]],
    key: str,
    kind: type,
) -> dict[int, object]:
    answers: dict[int, object] = {}
    for start in range(0, len(rows), BACK_BATCH):
        part = rows[start : start + BACK_BATCH]
        ids = [cast("int", r["id"]) for r in part]
        messages: tuple[Message, ...] = (
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({body_key: part}, ensure_ascii=False)},
        )
        got, _ = ask(
            chat,
            messages,
            lambda t, i=ids: _by_id(t, i, key, kind),
            reprompt=lambda why: f"That reply was rejected: {why}. Reply again for every id.",
            label="back",
            retries=3,
            sleep=time.sleep,
        )
        answers.update(got)
    return answers


def norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if unicodedata.category(ch)[0] in "LN")


def _bigrams(text: str) -> Counter[str]:
    return Counter(text[i : i + 2] for i in range(max(len(text) - 1, 1)))


def dice(a: str, b: str) -> float:
    """Dice overlap of the character bigrams of two sentences, 0 to 1."""
    x, y = _bigrams(norm(a)), _bigrams(norm(b))
    total = x.total() + y.total()
    return 2 * (x & y).total() / total if total else 0.0


def unit_text(cues: Sequence[Cue], ids: Sequence[int], code: str) -> str:
    said = {c.id: c.zh for c in cues}
    glue = "" if code in ("zh-TW", "zh-CN") else " "
    return glue.join(said.get(i, "") for i in ids).strip()


def back_translate(out: Path, chat: ChatFn) -> None:
    folder = out / "back"
    folder.mkdir(parents=True, exist_ok=True)
    for path in sorted((out / "runs/full").glob("*.json")):
        route, _, rest = path.name.partition(".")
        code = rest.removesuffix(".json")
        if route not in ROUTES:
            continue
        result = folder / f"{route}.{code}.json"
        if result.exists():
            continue
        rows: list[dict[str, object]] = []
        for talk in TALKS:
            _, units, back = sampled(out, talk)
            source = talk_cues(talk)
            made = parse_subs(read_text_file(out / "runs" / talk / path.name))
            for ids in (u for u in units if u[0] in back):
                row: dict[str, object] = {"id": len(rows) + 1, "talk": talk, "unit": ids[0]}
                row["original"] = flat_ja(source, ids)
                row["text"] = unit_text(made, ids, code)
                rows.append(row)
        asked = [{"id": r["id"], "text": r["text"]} for r in rows]
        name = "Traditional Chinese" if code == "zh-TW" else target(code).name
        back_ja = _ask_all(chat, _BACK_SYSTEM.format(name=name), "translate", asked, "ja", str)
        pairs = [
            {"id": r["id"], "original": r["original"], "other": back_ja[cast("int", r["id"])]}
            for r in rows
        ]
        scored = _ask_all(chat, _JUDGE_SYSTEM, "pairs", pairs, "score", int)
        for r in rows:
            i = cast("int", r["id"])
            r["back"] = back_ja[i]
            r["dice"] = round(dice(cast("str", r["original"]), cast("str", back_ja[i])), 3)
            r["judge"] = scored[i]
        result.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"back {route}.{code}: {len(rows)} sentences", flush=True)


def serve(out: Path, work: Callable[[ChatFn], None]) -> None:
    with LlamaServer(
        Path(os.environ.get(SERVER_ENV) or ASSETS / SERVER),
        ASSETS / MODEL,
        log_path=out / f"llama-server-{os.getpid()}.log",
        ctx=8192,
    ) as running:
        config = LlmConfig(running.base_url, "local", extra_body={**NO_THINK, "seed": LLM_SEED})
        work(json_chat(config))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=("pick", "run", "back"))
    parser.add_argument("out", type=Path)
    parser.add_argument("--targets", nargs="*", default=list(TARGETS))
    parser.add_argument("--routes", nargs="*", default=list(ROUTES), choices=ROUTES)
    parser.add_argument("--talks", nargs="*", default=list(TALKS), choices=list(TALKS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = cast("Path", args.out)
    if args.command == "pick":
        pick(out)
    elif args.command == "run":
        (out / "runs").mkdir(parents=True, exist_ok=True)
        talks, targets, routes = cast("list[str]", args.talks), args.targets, args.routes

        def run(chat: ChatFn) -> None:
            for talk in talks:
                Runner(out, chat).talk(talk, targets, routes)

        serve(out, run)
    else:
        serve(out, lambda chat: back_translate(out, chat))


if __name__ == "__main__":
    main()
