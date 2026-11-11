#!/usr/bin/env bash
# Rerun the P22 ASR matrix, one GPU job at a time. Usage: scripts/p22_run_matrix.sh WAV_DIR OUT_DIR
set -u
W=${1:?wav dir}; O=${2:?out dir}
run() { uv run python scripts/p22_asr.py "$@" || echo "FAILED: $*"; }
for v in cedec kirby; do
  for e in whisper kotoba qwen3; do
    run $e "$W/$v.wav" --mode chunks --lang ja --out "$O"
    if [ $e = qwen3 ]; then run $e "$W/$v.wav" --mode whole --lang ja --engine-vad --out "$O"
    else run $e "$W/$v.wav" --mode whole --lang ja --out "$O"; fi
  done
done
for l in en auto; do
  run whisper "$W/kirby.wav" --mode whole --lang $l --out "$O"
  run whisper "$W/kirby.wav" --mode chunks --lang $l --out "$O"
  run qwen3 "$W/kirby.wav" --mode chunks --lang $l --out "$O"
done
