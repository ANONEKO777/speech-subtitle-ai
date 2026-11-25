"""Z0 E2: a Taiwanese-voice proxy for Taiwanese Mandarin speech, with a known Traditional text.

    uv run python scripts/zh_z0_tts.py --count 120

There is no public Taiwanese audio in this round (Common Voice needs an account), so the Windows
voice `Microsoft Hanhan Desktop` (zh-TW) reads sentences of the repository's own Traditional
Chinese text (Taiwan wording). It is clean, synthetic speech: it shows which script an engine
writes for a Taiwan voice and how a prompt moves it, not how an engine does on a real speaker.
Output: `.work/zh-z0/tts/` (wavs at 16 kHz mono 16-bit and `manifest.json`).
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys

from zh_z0_text import ROOT, WORK, write_json

TTS = WORK / "tts"
SENTENCE = re.compile(r"[^。！？\n]{10,45}[。！？]")
HAN = re.compile("[㐀-鿿]")
PS = r"""
param([string]$Text, [string]$Out)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Hanhan Desktop')
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($Out, $fmt)
$s.Speak($Text)
$s.Dispose()
"""


def sentences() -> list[str]:
    found: list[str] = []
    for path in (
        ROOT / "README.zh-TW.md",
        ROOT / "docs" / "ZH-SOURCE-PLAN.zh-TW.md",
        ROOT / "docs" / "SPEC.md",
    ):
        for match in SENTENCE.finditer(path.read_text(encoding="utf-8")):
            text = match.group(0).strip()
            if len(HAN.findall(text)) >= 0.9 * len(text.replace("，", "").replace("、", "")):
                found.append(text)
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    args = parser.parse_args()
    TTS.mkdir(parents=True, exist_ok=True)
    script = TTS / "speak.ps1"
    script.write_text(PS, encoding="utf-8-sig")
    chosen = random.Random(20261126).sample(sentences(), args.count)
    manifest: dict[str, str] = {}
    for index, text in enumerate(chosen):
        out = TTS / f"t{index:03d}.wav"
        if not out.exists():
            subprocess.run(  # noqa: S603
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 "-Text", text, "-Out", str(out)],
                check=True,
            )  # fmt: skip
        manifest[out.stem] = text
    write_json(TTS / "manifest.json", manifest)
    print(f"{len(manifest)} sentences spoken")
    return 0


if __name__ == "__main__":
    sys.exit(main())
