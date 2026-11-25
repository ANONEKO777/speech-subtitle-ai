#!/bin/sh
# Z0 E1 speed: 2 rounds, alternating, over every 5th FLEURS utterance (189 files, about 39 minutes
# of audio). Whisper turbo, Qwen3-ASR with the aligner, Qwen3-ASR without it. Run from the
# repository root with PYTHONPATH=<root>:<root>/scripts and PY=<the repo's Python>.
PY="${PY:-python}"
run() { "$PY" scripts/zh_z0_asr.py "$@" || echo "FAILED: $*"; }
for round in ${ROUNDS:-1 2}; do
  run --tag sp-w-$round --engine whisper --lang zh --subset every5
  run --tag sp-q-$round --engine qwen3 --lang zh --subset every5
  run --tag sp-qn-$round --engine qwen3 --lang zh --subset every5 --no-aligner
done
