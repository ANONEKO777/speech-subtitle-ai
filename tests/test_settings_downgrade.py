"""An earlier build refuses a settings.json with a key it does not know and falls back to the
defaults, so a person who goes back a version would lose every setting. These are the keys the
builds already installed accept. A new preference that only the window reads (the update check at
start is one) belongs in the window's own storage instead."""

from typing import cast

from backend.manager.settings import AppSettings, LlmSettings, LlmSource, settings_json

RELEASED_TOP = {"schema_version", "profile", "llm", "registry_url", "ui_language"}
RELEASED_LLM = {"source", "ollama_url", "ollama_model", "cloud_url", "cloud_model", "cloud_consent"}


def test_settings_json_holds_only_keys_an_installed_build_reads() -> None:
    written = settings_json(
        AppSettings(llm=LlmSettings(source=LlmSource.OLLAMA, ollama_model="qwen3:8b"))
    )
    assert set(written) <= RELEASED_TOP, (
        f"{sorted(set(written) - RELEASED_TOP)}: an earlier build voids this settings.json"
    )
    llm = cast("dict[str, object]", written["llm"])
    assert set(llm) <= RELEASED_LLM, f"{sorted(set(llm) - RELEASED_LLM)}: an earlier build voids it"
