"""Check one translated language of a project, and back-translate a sample of its cues.

    python scripts/check_languages.py PROJECT_DIR --lang ja --out OUT_DIR [--back 20]

Structure checks need no model: the cue count and ids equal the English, no two cues overlap, the
script check of the language finds no error, and the SRT file agrees with the cue file. With
`--back N` a local llama-server starts, N cues are chosen with a fixed seed, each is translated
back to English by the same model, and the same model scores how well the back-translation keeps
the meaning of the original English (1 to 5). The table goes to OUT_DIR as markdown and json.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar, cast

from backend.core.languages import Language, get
from backend.core.model import Cue
from backend.core.subtitle_io import parse_srt, parse_subs, read_text_file
from backend.llm.ask import ChatFn, ReplyError, ask, parse_json_reply
from backend.llm.client import Message

T = TypeVar("T")
SEED = 18
PASS_SCORE = 4

BACK_SYSTEM = (
    "You translate a subtitle line from {language} into English. Reply with one JSON object "
    'and nothing else: {{"en": "the English translation"}}. Translate only the line you are '
    "given, as literally as natural English allows. Do not add anything."
)
JUDGE_SYSTEM = (
    "You compare two English subtitle lines. The first is the original. The second is an English "
    "back-translation of a translation of the original. Score how well the second keeps the "
    "meaning of the first: 5 same meaning, 4 same meaning with small wording or detail "
    "differences, 3 partly the same, 2 mostly different, 1 unrelated or wrong. Both lines may be "
    "a fragment of a sentence, so do not penalise for being incomplete. Reply with one JSON "
    'object and nothing else: {"score": 1, "reason": "one short sentence"}.'
)


@dataclass(frozen=True, slots=True)
class Structure:
    cues: int
    english_cues: int
    ids_equal: bool
    overlaps: int
    script_errors: list[str]
    kept_english: int
    empty: int
    srt_matches: bool


def structure(folder: Path, lang: Language) -> Structure:
    cues = parse_subs(read_text_file(folder / lang.files.subs))
    english = parse_subs(read_text_file(folder / "subs.en.json"))
    overlaps = sum(a.end_ms > b.start_ms for a, b in zip(cues, cues[1:], strict=False))
    errors = [
        f"cue {c.id}: {problem}"
        for c in cues
        if c.zh != c.en and (problem := lang.problem(c.zh, c.en))
    ]
    srt = parse_srt(read_text_file(folder / lang.files.srt), "zh")
    return Structure(
        len(cues),
        len(english),
        [c.id for c in cues] == [c.id for c in english],
        overlaps,
        errors,
        sum(c.zh == c.en for c in cues),
        sum(not c.zh for c in cues),
        [(c.start_ms, c.end_ms, c.zh) for c in srt] == [(c.start_ms, c.end_ms, c.zh) for c in cues],
    )


def sample(cues: list[Cue], count: int) -> list[Cue]:
    pool = [c for c in cues if c.zh != c.en and len(c.en.split()) >= 3]
    return sorted(random.Random(SEED).sample(pool, min(count, len(pool))), key=lambda c: c.id)


def _object(text: str) -> dict[str, object]:
    doc = parse_json_reply(text)
    if not isinstance(doc, dict):
        raise ReplyError("the reply must be one JSON object")
    return cast("dict[str, object]", doc)


def _text(doc: dict[str, object]) -> str:
    value = doc.get("en")
    if not isinstance(value, str) or not value.strip():
        raise ReplyError('"en" must be a non-empty string')
    return value.strip()


def _verdict(doc: dict[str, object]) -> tuple[int, str]:
    score, reason = doc.get("score"), doc.get("reason", "")
    if type(score) is not int or not 1 <= score <= 5:
        raise ReplyError('"score" must be an integer from 1 to 5')
    return score, str(reason)


def _ask(chat: ChatFn, system: str, user: str, parse: Callable[[dict[str, object]], T]) -> T:
    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    value, _ = ask(
        chat,
        messages,
        lambda text: parse(_object(text)),
        reprompt=lambda reason: f"That reply was rejected: {reason}. Reply again.",
        label="back-translation",
    )
    return value


def back_translate(chat: ChatFn, lang: Language, cues: list[Cue]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cue in cues:
        back = _ask(chat, BACK_SYSTEM.format(language=lang.name), cue.zh, _text)
        judged = json.dumps({"original": cue.en, "back_translation": back}, ensure_ascii=False)
        score, reason = _ask(chat, JUDGE_SYSTEM, judged, _verdict)
        rows.append(
            {
                "id": cue.id,
                "en": cue.en,
                "target": cue.zh,
                "back": back,
                "score": score,
                "reason": reason,
            }
        )
    return rows


def table(rows: list[dict[str, object]], lang: Language) -> str:
    lines = [
        f"| id | English | {lang.code} | back to English | score |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        cells = [str(r[k]).replace("|", "\\|").replace("\n", " ") for k in ("en", "target", "back")]
        lines.append(f"| {r['id']} | {cells[0]} | {cells[1]} | {cells[2]} | {r['score']} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--lang", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--back", type=int, default=0, metavar="N")
    parser.add_argument("--user-data", type=Path)
    args = parser.parse_args(argv)
    lang = get(args.lang)
    args.out.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"lang": lang.code}
    found = structure(args.project, lang)
    result["structure"] = asdict(found)
    ok = (
        found.cues == found.english_cues
        and found.ids_equal
        and found.overlaps == 0
        and not found.script_errors
        and found.srt_matches
    )
    print(f"{lang.code}: structure {'OK' if ok else 'FAILED'} {found}")
    if args.back:
        from backend.manager.resolve import Request, resolve

        cues = sample(parse_subs(read_text_file(args.project / lang.files.subs)), args.back)
        _, ports = resolve(Request(user_data=args.user_data), args.project)
        with ports.open_llm(threading.Event()) as session:
            rows = back_translate(session.translate, lang, cues)
        scores = [int(str(r["score"])) for r in rows]
        mean = round(sum(scores) / len(scores), 2)
        pass_rate = round(sum(s >= PASS_SCORE for s in scores) / len(scores), 2)
        result["back_translation"] = {"rows": rows, "mean": mean, "pass_rate": pass_rate}
        (args.out / f"back-{lang.code}.md").write_text(
            f"# Back-translation sample, {lang.code}\n\n"
            f"mean score {mean}, share scoring {PASS_SCORE} or more {pass_rate}\n\n"
            + table(rows, lang)
            + "\n",
            encoding="utf-8",
        )
    (args.out / f"check-{lang.code}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
