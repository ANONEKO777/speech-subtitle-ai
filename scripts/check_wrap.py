"""Re-export the bilingual ASS of a project's languages and count the bad line breaks. No LLM runs.

    python scripts/check_wrap.py PROJECT_FOLDER OUT_FOLDER CODE [CODE ...]

For each language it renders `subs.<code>.json` with the language's wrap rule into
`OUT_FOLDER/bilingual.en-<code>.ass`, then counts the soft breaks that fall inside a word (a
letter on both sides) and the lines that begin with a combining mark. Both must be 0.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from backend.core.languages import get
from backend.core.subtitle_io import parse_subs, read_text_file, render_ass, write_text_file

SOFT = chr(92) + "N{" + chr(92) + "q0}"
EN_MARK = chr(92) + "N{" + chr(92) + "rEn}"
_SOFT = re.compile(r"(.)" + re.escape(SOFT) + "(.)")


def count(ass: str) -> dict[str, int]:
    breaks = in_word = mark_starts = 0
    for line in ass.splitlines():
        if not line.startswith("Dialogue"):
            continue
        zh = line.split(",,", 1)[1].split(EN_MARK)[0]
        for m in _SOFT.finditer(zh):
            breaks += 1
            before, after = m.groups()
            in_word += _in_word(before, after)
            mark_starts += unicodedata.category(after).startswith("M")
    return {"breaks": breaks, "in_word": in_word, "mark_starts": mark_starts}


def _unspaced(char: str) -> bool:
    """Thai, kana and Han letters: scripts that break between letters by design."""
    return any(
        low <= char <= high
        for low, high in (
            ("฀", "๿"),
            ("぀", "ヿ"),
            ("㐀", "鿿"),
            ("豈", "﫿"),
            ("ｦ", "ﾟ"),
        )
    )


def _in_word(before: str, after: str) -> bool:
    return before.isalpha() and after.isalpha() and not _unspaced(before) and not _unspaced(after)


def main(folder: str, out: str, codes: list[str]) -> int:
    Path(out).mkdir(parents=True, exist_ok=True)
    bad = 0
    for code in codes:
        lang = get(code)
        cues = parse_subs(read_text_file(Path(folder) / lang.files.subs))
        ass = render_ass(cues, lang.wrap)
        write_text_file(Path(out) / lang.files.ass, ass)
        result = count(ass)
        bad += result["in_word"] + result["mark_starts"]
        print(code, lang.wrap.value, result)
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
