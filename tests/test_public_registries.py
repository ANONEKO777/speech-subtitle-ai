"""The lock files must name public package hosts only, so a fresh clone installs anywhere.

A machine that is set up with a private npm mirror writes that mirror's address into
`app/package-lock.json` on `npm install`. Nobody else can reach it, and CI fails on it.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NPM_HOST = "registry.npmjs.org"
PYPI_REGISTRY = "https://pypi.org/simple"


def test_npm_lock_resolves_every_package_from_the_public_registry() -> None:
    lock = json.loads((ROOT / "app" / "package-lock.json").read_text(encoding="utf-8"))
    hosts = {
        urlparse(entry["resolved"]).netloc
        for entry in lock["packages"].values()
        if "resolved" in entry
    }
    assert hosts == {NPM_HOST}


def test_npm_lock_uses_https_only() -> None:
    text = (ROOT / "app" / "package-lock.json").read_text(encoding="utf-8")
    assert not re.search(r'"resolved": "http://', text)


def test_uv_lock_uses_the_public_index_only() -> None:
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    registries = set(re.findall(r'registry = "([^"]+)"', text))
    assert registries == {PYPI_REGISTRY}
