#!/usr/bin/env bash
# Make a synthetic Japanese clip with known text (docs/p22/tts-ja.txt) using Qwen3-TTS through CrispASR.
# Usage: scripts/p22_tts_anchor.sh OUT_DIR TALKER.gguf CODEC.gguf   (GPU must be free)
set -eu
OUT=${1:?out dir}; TALKER=${2:?talker gguf}; CODEC=${3:?codec gguf}
BIN="${CRISPASR:-$(dirname "$0")/../runtimes/crispasr-v0.8.49-win-cuda/crispasr-windows-x86_64-cuda/crispasr.exe}"
FF="/c/Program Files/ffmpeg-n6.1-latest-win64-gpl-shared-6.1/bin/ffmpeg.exe"
mkdir -p "$OUT"; : > "$OUT/list.txt"; n=0
while IFS= read -r line; do
  n=$((n+1)); f=$(printf "%s/s%02d.wav" "$OUT" $n)
  "$BIN" --backend qwen3-tts-1.7b-customvoice -m "$TALKER" --codec-model "$CODEC" --voice ono_anna \
    --tts "$line" --tts-output "$f" > "$OUT/s$n.log" 2>&1
  echo "file '$f'" >> "$OUT/list.txt"
done < "$(dirname "$0")/../docs/p22/tts-ja.txt"
"$FF" -nostdin -v error -y -f concat -safe 0 -i "$OUT/list.txt" -ar 16000 -ac 1 -c:a pcm_s16le "$OUT/tts_ja.wav"
