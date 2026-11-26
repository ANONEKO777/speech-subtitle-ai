#!/bin/sh
# Z0 second batch: Taiwanese-voice proxy (E2), the operator's video (E5), language id (E4),
# then speed repeats (E1). One model process at a time. Run from the repository root with
# PYTHONPATH=<root>:<root>/scripts and PY=<the repo's Python>.
PY="${PY:-python}"
TTS=".work/zh-z0/tts"
[ -d "$TTS" ] || TTS="$(cd ../.. && pwd)/.work/zh-z0/tts"
run() { "$PY" scripts/zh_z0_asr.py "$@" || echo "FAILED: $*"; }
step() { "$PY" "$@" || echo "FAILED: $*"; }
run --tag tts-w --engine whisper --lang zh --wav-dir "$TTS"
run --tag tts-w-hant --engine whisper --lang zh --prompt "以下是繁體中文的句子。" --wav-dir "$TTS"
run --tag tts-q --engine qwen3 --lang zh --wav-dir "$TTS"
run --tag tts-q-auto --engine qwen3 --lang auto --wav-dir "$TTS"
run --tag tts-q-hant --engine qwen3 --lang zh-Hant --wav-dir "$TTS"
step scripts/zh_z0_e5_asr.py --tag e5-w --engine whisper --lang zh
step scripts/zh_z0_e5_asr.py --tag e5-q --engine qwen3 --lang zh
step scripts/zh_z0_e5_asr.py --tag e5-q-hant --engine qwen3 --lang zh-Hant
step scripts/zh_z0_e5_asr.py --tag e5-w-merged --engine whisper --lang zh --unspaced-merge
step scripts/zh_z0_detect.py run --seconds 5 --per-lang 150
step scripts/zh_z0_detect.py run --seconds 2 --per-lang 150
