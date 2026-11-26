"""Z0 E5: which names of the anime video the translator garbles, and how often.

    uv run python scripts/zh_z0_names.py [draft|standin]

For each name (Traditional Chinese as the cue holds it), it counts the cues of the `ref` set (the
hard-sub lines) and the `e5` set (the ASR cues) that hold the name, how many English and Japanese
translations of those cues contain an accepted rendering, and prints a few that do not. The
accepted renderings are the official English and Japanese names of the series as I know them (my
own knowledge, not checked against a source), so a "miss" is a difference from that list, to be
read by a person, not proof of an error.
"""

from __future__ import annotations

import re
import sys
from typing import Any, cast

from zh_z0_text import RUNS, read_json

NAMES: dict[str, tuple[str, str]] = {
    "莉可": (r"Riko", r"リコ"),
    "阿庇斯": (r"Abyss", r"アビス"),
    "深界": (r"Abyss|Depth|Deep|Layer|Realm|Underworld", r"深界|アビス|深層|層"),
    "探窟家": (r"Cave Raider|Raider|Delver", r"探窟家"),
    "赤笛": (r"Red Whistle", r"赤笛"),
    "青笛": (r"Blue Whistle", r"青笛"),
    "蒼笛": (r"Blue Whistle", r"青笛|蒼笛"),
    "白笛": (r"White Whistle", r"白笛"),
    "星之羅盤": (r"Star Compass|Compass of the Stars", r"星の羅針盤|星の羅盤"),
    "奧森": (r"Ozen", r"オーゼン"),
    "不動卿": (r"Immovable|Ozen", r"不動卿"),
    "孤兒院": (r"Orphanage", r"孤児院"),
    "巨人之杯": (r"Giant'?s'? Cup|Cup of (the )?Giants?", r"巨人の杯"),
    "千人楔": (r"Thousand|Wedge", r"千人楔"),
}


def main() -> int:
    variant = sys.argv[1] if len(sys.argv) > 1 else "draft"
    print("| name | cues | English accepted | Japanese accepted |")
    print("|---|---|---|---|")
    misses: dict[str, list[str]] = {}
    for name, (english, japanese) in NAMES.items():
        counts = {"cues": 0, "en": 0, "ja": 0}
        for target, pattern in (("en", english), ("ja", japanese)):
            for set_name in ("ref", "e5"):
                path = RUNS / f"tr-{variant}-{set_name}-{target}.json"
                if not path.exists():
                    continue
                rows = cast("list[dict[str, Any]]", read_json(path)["rows"])
                for row in rows:
                    if name not in str(row["src"]):
                        continue
                    if target == "en":
                        counts["cues"] += 1
                    counts[target] += 1 if re.search(pattern, str(row["zh"]), re.IGNORECASE) else 0
                    if not re.search(pattern, str(row["zh"]), re.IGNORECASE):
                        misses.setdefault(f"{name} {target}", []).append(str(row["zh"])[:48])
        if counts["cues"]:
            print(f"| {name} | {counts['cues']} | {counts['en']} | {counts['ja']} |")
    for key, lines in misses.items():
        print(f"- {key}: " + " / ".join(lines[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
