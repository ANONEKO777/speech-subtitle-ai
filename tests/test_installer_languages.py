"""The Windows installer speaks the four window languages and follows the operating system.

Tauri uses a file named in `customLanguageFiles` instead of its own file for that language, so a
custom file that defines only some of the template's messages leaves the others blank. With no
language selector, NSIS shows the language of the operating system, or the first listed one when
the system language is not listed. The window falls back to English, so the installer does too.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import NotRequired, TypedDict

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "app" / "src-tauri" / "tauri.conf.json"

LANGUAGES = {
    "English": "ENGLISH",
    "TradChinese": "TRADCHINESE",
    "SimpChinese": "SIMPCHINESE",
    "Japanese": "JAPANESE",
}

# The messages Tauri 2.12's NSIS template reads, from its built-in language files.
TAURI_MESSAGES = {
    "addOrReinstall",
    "alreadyInstalled",
    "alreadyInstalledLong",
    "appRunning",
    "appRunningOkKill",
    "chooseMaintenanceOption",
    "chooseHowToInstall",
    "createDesktop",
    "dontUninstall",
    "dontUninstallDowngrade",
    "failedToKillApp",
    "installingWebview2",
    "newerVersionInstalled",
    "older",
    "olderOrUnknownVersionInstalled",
    "silentDowngrades",
    "unableToUninstall",
    "uninstallApp",
    "uninstallBeforeInstalling",
    "unknown",
    "webview2AbortError",
    "webview2DownloadError",
    "webview2DownloadSuccess",
    "webview2Downloading",
    "webview2InstallError",
    "webview2InstallSuccess",
    "deleteAppData",
}

LANG_STRING = re.compile(r'^LangString (\w+) \$\{LANG_(\w+)\} "(.*)"$')


class NsisConfig(TypedDict):
    languages: list[str]
    customLanguageFiles: dict[str, str]
    displayLanguageSelector: NotRequired[bool]


def nsis_config() -> NsisConfig:
    return json.loads(CONFIG.read_text(encoding="utf-8"))["bundle"]["windows"]["nsis"]


def custom_file(language: str) -> Path:
    return (CONFIG.parent / nsis_config()["customLanguageFiles"][language]).resolve()


def messages(path: Path) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith(";"):
            continue
        match = LANG_STRING.match(line)
        assert match, f"{path.name}: not a LangString line: {line}"
        found.append((match[1], match[2], match[3]))
    return found


def test_the_installer_offers_the_four_window_languages_with_english_first() -> None:
    config = nsis_config()

    assert config["languages"] == list(LANGUAGES)
    assert sorted(config["customLanguageFiles"]) == sorted(LANGUAGES)
    assert config.get("displayLanguageSelector", False) is False


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_each_language_file_defines_every_message_once_for_its_own_language(language: str) -> None:
    found = messages(custom_file(language))
    names = [name for name, _, _ in found]

    assert sorted(names) == sorted(TAURI_MESSAGES)
    assert {lang for _, lang, _ in found} == {LANGUAGES[language]}
    assert all(text.strip() for _, _, text in found)


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_each_language_file_uses_the_nsis_product_name_not_a_template_variable(
    language: str,
) -> None:
    text = custom_file(language).read_text(encoding="utf-8")

    assert "{{" not in text
    assert "Video Subtitle Translator" not in text


@pytest.mark.parametrize("language", ["TradChinese", "SimpChinese", "Japanese"])
def test_each_translated_file_is_written_in_its_language(language: str) -> None:
    texts = [text for name, _, text in messages(custom_file(language)) if name != "unknown"]
    english = {text for _, _, text in messages(custom_file("English"))}

    assert not english.intersection(texts)
    assert all(re.search(r"[぀-ヿ一-鿿]", text) for text in texts)


def makensis() -> str | None:
    found = shutil.which("makensis")
    if found:
        return found
    tauri = Path(os.environ.get("LOCALAPPDATA", "")) / "tauri" / "NSIS" / "makensis.exe"
    return str(tauri) if tauri.is_file() else None


def test_makensis_accepts_the_language_files_with_no_missing_message(tmp_path: Path) -> None:
    tool = makensis()
    if tool is None:
        pytest.skip("makensis is not installed (Tauri downloads it on the first installer build)")
    includes = "\n".join(f'!include "{custom_file(lang)}"' for lang in LANGUAGES)
    languages = "\n".join(f'!insertmacro MUI_LANGUAGE "{lang}"' for lang in LANGUAGES)
    uses = "\n".join(f'  DetailPrint "$({name})"' for name in sorted(TAURI_MESSAGES))
    script = tmp_path / "languages.nsi"
    script.write_text(
        "Unicode true\n!pragma warning error all\n!include MUI2.nsh\n"
        '!define PRODUCTNAME "Probe"\n!define VERSION "0.0.0"\n'
        f'OutFile "{tmp_path / "probe.exe"}"\n'
        "!insertmacro MUI_PAGE_INSTFILES\n"
        f"{languages}\n{includes}\nSection\n{uses}\nSectionEnd\n",
        encoding="utf-8-sig",
    )

    run = subprocess.run([tool, "-V2", str(script)], capture_output=True, text=True, check=False)  # noqa: S603

    assert run.returncode == 0, run.stdout + run.stderr
