#!/bin/sh
# Z0 E1/E2: every ASR configuration over the whole FLEURS Mandarin test split, one process at a time.
# Run from the repository root with PYTHONPATH=<root>:<root>/scripts and the repo's Python.
PY="${PY:-python}"
run() { "$PY" scripts/zh_z0_asr.py "$@" || echo "FAILED: $*"; }
run --tag w-zh --engine whisper --lang zh
run --tag w-zh-prompt-hant --engine whisper --lang zh --prompt "以下是繁體中文的句子。"
run --tag w-zh-prompt-simp --engine whisper --lang zh --prompt "以下是普通话的句子。"
run --tag w-auto --engine whisper --lang auto
run --tag q-zh --engine qwen3 --lang zh
run --tag q-auto --engine qwen3 --lang auto
run --tag q-zh-hant --engine qwen3 --lang zh-Hant
run --tag q-zh-noalign --engine qwen3 --lang zh --no-aligner
