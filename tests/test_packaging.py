import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_exact_editable_install_can_import_without_the_dev_group() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    exact = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["dev-mode-exact"]
    runtime = [
        re.split(r"[<>=!~ ;\[]", dep, maxsplit=1)[0] for dep in pyproject["project"]["dependencies"]
    ]
    assert not exact or "editables" in runtime
