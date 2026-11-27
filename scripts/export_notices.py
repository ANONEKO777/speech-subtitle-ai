"""Write `app/src/i18n/notices.backend.json` from the registry in `backend/core/notices.py`.

Run it after you add or change a notice: `python scripts/export_notices.py`.
`tests/test_notices.py` fails while the file and the registry differ.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.notices import registry_file  # noqa: E402

if __name__ == "__main__":
    target = ROOT / "app" / "src" / "i18n" / "notices.backend.json"
    target.write_text(registry_file(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")
