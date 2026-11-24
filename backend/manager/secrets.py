"""Where the cloud API key lives: encrypted for the current Windows user, in the user data folder.

The key never goes into `settings.json`, a log line, an API response or a project folder."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

from backend.manager.platforms import WIN_X64, detect_platform

SECRETS_DIR = "secrets"
LLM_KEY = "llm_api_key"
_ENTROPY = b"video-subtitle-translator/v1"
_UI_FORBIDDEN = 0x1


class SecretError(RuntimeError):
    pass


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def clear(self, name: str) -> None: ...


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_of(data: bytes) -> tuple[_Blob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _transform(data: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise SecretError("storing the API key needs Windows DPAPI")
    source, _keep = _blob_of(data)
    entropy, _keep_entropy = _blob_of(_ENTROPY)
    out = _Blob()
    crypt32 = ctypes.windll.crypt32
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = call(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        _UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise SecretError(f"Windows DPAPI failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class DpapiSecretStore:
    def __init__(self, user_data: Path) -> None:
        self._dir = user_data / SECRETS_DIR
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.dpapi"

    def get(self, name: str) -> str | None:
        with self._lock:
            try:
                blob = self._path(name).read_bytes()
            except FileNotFoundError:
                return None
            return _transform(blob, protect=False).decode("utf-8")

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            target = self._path(name)
            temp = target.with_name(target.name + ".tmp")
            with temp.open("wb") as out:
                out.write(_transform(value.encode("utf-8"), protect=True))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, target)

    def clear(self, name: str) -> None:
        with self._lock:
            self._path(name).unlink(missing_ok=True)


class MemorySecretStore:
    """For tests, and for a machine without DPAPI."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def clear(self, name: str) -> None:
        self._values.pop(name, None)


KEY_NOT_AVAILABLE_MESSAGE = (
    "這個版本在 Mac 上還不能儲存雲端 API 金鑰。請改用本機模型（預設）或 Ollama；"
    "雲端金鑰的儲存之後會再加上。"
)


class UnavailableSecretStore:
    """For a platform with no key store yet (macOS): nothing is saved and saving says so in plain
    words, so the settings page shows a refusal and not an error. Reading finds no key."""

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None:
        raise SecretError(KEY_NOT_AVAILABLE_MESSAGE)

    def clear(self, name: str) -> None:
        return None


def default_secret_store(user_data: Path, platform: str | None = None) -> SecretStore:
    """The key store of `platform` (this machine's when None): DPAPI on Windows, none on a Mac."""
    platform = detect_platform() if platform is None else platform
    if platform == WIN_X64:
        return DpapiSecretStore(user_data)
    return UnavailableSecretStore()
