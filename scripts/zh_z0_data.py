"""Z0 data step: download the FLEURS test split of Mandarin, Japanese, Korean and English, unpack it.

    uv run python scripts/zh_z0_data.py fetch      # downloads into .work/zh-z0/data (about 1.5 GB)
    uv run python scripts/zh_z0_data.py extract    # unpacks the wavs, writes manifest.json per language

FLEURS (`google/fleurs` on Hugging Face) is licensed CC BY 4.0 (the dataset card's `license:` field
and its closing paragraph). It is public and not gated. Only the `test` split of each language is
taken. Nothing here is committed.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from zh_z0_text import DATA, FLEURS_LANGS, read_tsv, write_json

BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"


def fetch() -> None:
    for code in FLEURS_LANGS.values():
        folder = DATA / code
        folder.mkdir(parents=True, exist_ok=True)
        for name, url in (
            ("test.tsv", f"{BASE}/{code}/test.tsv"),
            ("test.tar.gz", f"{BASE}/{code}/audio/test.tar.gz"),
        ):
            target = folder / name
            if target.exists() and target.stat().st_size > 0:
                continue
            print(f"downloading {url}", flush=True)
            urllib.request.urlretrieve(url, target)  # noqa: S310


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def to_pcm16(source: Path, target: Path) -> None:
    """FLEURS wavs are 32-bit float; the app's own audio step gives 16 kHz mono 16-bit, so the
    engines get the same format here."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(target)],
        check=True,
    )  # fmt: skip


def extract() -> None:
    inventory: dict[str, dict[str, object]] = {}
    for lang, code in FLEURS_LANGS.items():
        folder = DATA / code
        wavs = folder / "pcm"
        raw = folder / "raw"
        wavs.mkdir(exist_ok=True)
        raw.mkdir(exist_ok=True)
        archive = folder / "test.tar.gz"
        if not any(raw.iterdir()):
            with tarfile.open(archive) as tar:
                for member in tar:
                    if member.isfile() and member.name.endswith(".wav"):
                        member.name = Path(member.name).name
                        tar.extract(member, raw, filter="data")
        todo = [p for p in sorted(raw.iterdir()) if not (wavs / p.name).exists()]
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(to_pcm16, todo, [wavs / p.name for p in todo]))
        rows: list[dict[str, object]] = []
        for index, fields in enumerate(read_tsv(folder / "test.tsv")):
            file = fields[1]
            path = wavs / file
            if not path.exists():
                continue
            with wave.open(str(path), "rb") as reader:
                seconds = reader.getnframes() / reader.getframerate()
                rate = reader.getframerate()
                channels = reader.getnchannels()
            rows.append(
                {
                    "key": f"{lang}-{index:04d}",
                    "file": file,
                    "sentence_id": fields[0],
                    "raw": fields[2],
                    "normalized": fields[3],
                    "seconds": seconds,
                    "gender": fields[6],
                    "rate": rate,
                    "channels": channels,
                }
            )
        write_json(folder / "manifest.json", rows)
        inventory[lang] = {
            "fleurs_config": code,
            "utterances": len(rows),
            "hours": round(sum(float(str(r["seconds"])) for r in rows) / 3600, 2),
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": sha256(archive),
            "sample_rates": sorted({int(str(r["rate"])) for r in rows}),
            "channels": sorted({int(str(r["channels"])) for r in rows}),
        }
        print(lang, inventory[lang], flush=True)
    write_json(DATA / "INVENTORY.json", inventory)


if __name__ == "__main__":
    {"fetch": fetch, "extract": extract}[sys.argv[1]]()
