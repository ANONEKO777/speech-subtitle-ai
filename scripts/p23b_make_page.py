"""P23b lever: build the self-contained label page from a `p23b_sample.py` manifest.

The page lists the clips in the manifest's presentation order and carries only the segment id and
the clip's relative path. It holds no stratum, no model guess, and no timestamp, so the labeller
cannot be biased by them. The logic of the page is `p23b_page/logic.js`, which `node` tests run.

    uv run python scripts/p23b_make_page.py [--manifest M.json] [--out label.html]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = Path(".work/p23b-labels/manifest.json")


def page_items(manifest: dict[str, Any]) -> list[dict[str, str]]:
    segments = sorted(manifest["segments"], key=lambda s: s["position"])
    return [{"id": s["id"], "clip": f"clips/{s['id']}.mp3"} for s in segments]


def build_page(manifest: dict[str, Any]) -> str:
    items = page_items(manifest)
    set_id = hashlib.sha256(json.dumps(items).encode()).hexdigest()[:12]
    html = (HERE / "p23b_page/template.html").read_text(encoding="utf-8")
    logic = (HERE / "p23b_page/logic.js").read_text(encoding="utf-8")
    for marker, value in (
        ("/*__LOGIC__*/", logic),
        ('/*__SET_ID__*/""', json.dumps(set_id)),
        ("/*__ITEMS__*/[]", json.dumps(items)),
    ):
        assert html.count(marker) == 1, marker
        html = html.replace(marker, value)
    return html


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_MANIFEST.parent / "label.html")
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.out.write_text(build_page(manifest), encoding="utf-8")
    print(f"wrote {args.out} ({len(page_items(manifest))} clips)")


if __name__ == "__main__":
    main()
