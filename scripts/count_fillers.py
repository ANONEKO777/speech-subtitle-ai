"""Count the you-know fillers in the Traditional Chinese cues of a project, before and after the
English-aware clean-up.

    python scripts/count_fillers.py SUBS_ZH_JSON [SUBS_ZH_JSON ...]

For each file it prints how many cues hold 你知道 or 你知 as written, how many of those sit
under an English cue that says "you know" as a filler, and how many remain after
`drop_fillers` is applied to every cue with its English.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from backend.core.fillers import drop_fillers, english_you_know_filler
from backend.core.subtitle_io import parse_subs, read_text_file

_YOU_KNOW = re.compile(r"你知(?:不知)?道?")


def count(path: Path) -> dict[str, int]:
    cues = parse_subs(read_text_file(path))
    written = [c for c in cues if _YOU_KNOW.search(c.zh)]
    on_filler = [c for c in written if english_you_know_filler(c.en)]
    after = [c for c in cues if _YOU_KNOW.search(drop_fillers(c.zh, c.en))]
    return {
        "cues": len(cues),
        "cues_with_ni_zhi": len(written),
        "occurrences": sum(len(_YOU_KNOW.findall(c.zh)) for c in cues),
        "on_you_know_filler_cue": len(on_filler),
        "cues_with_ni_zhi_after_clean": len(after),
        "occurrences_after_clean": sum(
            len(_YOU_KNOW.findall(drop_fillers(c.zh, c.en))) for c in cues
        ),
    }


def main(paths: list[str]) -> int:
    for path in paths:
        print(path, count(Path(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
