"""Estimate how many Chinese cues hold words that belong to a neighbouring English cue.

A cue is misaligned when either signal fires. Both are asked of a local llama-server, one cue
at a time.
- Judge: shown the previous, own and next English cue as A, B, C, the model names the one the
  Chinese translates. Any answer but B is a miss.
- Leak: the Chinese is translated back to English. Its content words that the cue's own English
  lacks but a neighbour's English has, outweighing the words shared with its own English, are a
  leak. This catches a clause pulled from a neighbour, which the judge often misses.

    uv run python scripts/check_alignment.py --subs subs.zh-TW.json --sample 20 --seed 20261104
    uv run python scripts/check_alignment.py --subs subs.zh-TW.json --cues 118 167 194 302 304
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from backend.core.model import Cue
from backend.core.subtitle_io import parse_subs, read_text_file
from backend.llm import client
from backend.llm.client import LlmConfig, Message

LEAK_THRESHOLD = 0.25
_STOP = frozenset(
    "the a an and or but so if then than that this these those it its is are was were be been "
    "being am do does did have has had to of in on at by for with from as into about up out "
    "you your we our they their he she his her i me my not no yes just can could will would "
    "should may might what which who how when where why there here also very really like "
    "right now all any some more most one get got going know think".split()
)
_JUDGE_PROMPT = (
    "You compare a Chinese subtitle line with three consecutive English subtitle fragments A, B, "
    "C, pieces of one continuous speech. Decide which English fragment the Chinese line "
    "translates: the one whose words it expresses. Reply with one JSON object only: "
    '{"answer": "A"}, with A, B or C.'
)
_BACK_PROMPT = (
    "Translate this Traditional Chinese subtitle fragment back into English, word for word. "
    "It is a piece of a longer sentence: translate only what it says, never complete it or add "
    "words. Reply with the English only."
)


@dataclass(frozen=True, slots=True)
class CueScore:
    id: int
    own: float
    leak_prev: float
    leak_next: float
    judged: str

    @property
    def leak(self) -> float:
        return max(self.leak_prev, self.leak_next)

    @property
    def misaligned(self) -> bool:
        leaks = self.leak >= LEAK_THRESHOLD and self.leak > self.own
        return leaks or self.judged != "B"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def content_words(text: str) -> frozenset[str]:
    words = (re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w for w in _tokens(text))
    return frozenset(w for w in words if len(w) > 2 and w not in _STOP)


def score(back: str, previous: str, own: str, following: str) -> tuple[float, float, float]:
    words = content_words(back)
    if not words:
        return 0.0, 0.0, 0.0
    mine = content_words(own)
    return (
        len(words & mine) / len(words),
        len(words & (content_words(previous) - mine)) / len(words),
        len(words & (content_words(following) - mine)) / len(words),
    )


def back_translate(config: LlmConfig, cue: Cue) -> str:
    messages: list[Message] = [
        {"role": "system", "content": _BACK_PROMPT},
        {"role": "user", "content": cue.zh},
    ]
    return client.chat(config, messages).strip()


def judge(config: LlmConfig, previous: str, cue: Cue, following: str) -> str:
    shown = f"A: {previous}\nB: {cue.en}\nC: {following}\n\nChinese: {cue.zh}"
    messages: list[Message] = [
        {"role": "system", "content": _JUDGE_PROMPT},
        {"role": "user", "content": shown},
    ]
    reply = cast("dict[str, object]", json.loads(client.chat(config, messages, json_mode=True)))
    return str(reply.get("answer", "?")).strip().upper()


def check(config: LlmConfig, cues: Sequence[Cue], ids: Sequence[int]) -> list[CueScore]:
    index = {cue.id: i for i, cue in enumerate(cues)}
    scores: list[CueScore] = []
    for cue_id in ids:
        i = index[cue_id]
        cue = cues[i]
        previous = cues[i - 1].en if i else ""
        following = cues[i + 1].en if i + 1 < len(cues) else ""
        own, leak_prev, leak_next = score(back_translate(config, cue), previous, cue.en, following)
        verdict = judge(config, previous, cue, following)
        scores.append(CueScore(cue.id, own, leak_prev, leak_next, verdict))
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subs", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--cues", type=int, nargs="*", help="check exactly these cue ids")
    parser.add_argument("--sample", type=int, help="check N random cues instead of all")
    parser.add_argument("--seed", type=int, default=20261104)
    args = parser.parse_args()
    cues = parse_subs(read_text_file(args.subs))
    ids = [c.id for c in cues if c.zh]
    if args.cues:
        ids = list(args.cues)
    elif args.sample:
        ids = sorted(random.Random(args.seed).sample(ids[1:-1], args.sample))
    no_think = {"chat_template_kwargs": {"enable_thinking": False}}
    config = LlmConfig(args.base_url, args.model, extra_body=no_think)
    scores = check(config, cues, ids)
    bad = [s for s in scores if s.misaligned]
    for s in scores:
        flag = "MISALIGNED" if s.misaligned else "ok"
        leaks = f"own={s.own:.2f} prev={s.leak_prev:.2f} next={s.leak_next:.2f}"
        print(f"{s.id:4d} judge={s.judged} {leaks} {flag}")
    rate = len(bad) / len(scores)
    summary = {
        "checked": len(scores),
        "misaligned": len(bad),
        "rate": round(rate, 3),
        "ids": [s.id for s in bad],
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
