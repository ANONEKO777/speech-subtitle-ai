#!/bin/sh
# Z0 E6: the talk, whole, through the app's ASR path. Run after `zh_z0_e6.py audio`.
PY="${PY:-python}"
step() { "$PY" scripts/zh_z0_e5_asr.py --set e6 "$@" || echo "FAILED: $*"; }
step --tag e6-w --engine whisper --lang zh
step --tag e6-q --engine qwen3 --lang zh
step --tag e6-q-hant --engine qwen3 --lang zh-Hant
step --tag e6-w-prompt --engine whisper --lang zh --prompt "以下是繁體中文的句子。"
