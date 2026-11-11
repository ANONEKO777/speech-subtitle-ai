# Test fixtures

## en_15s.wav

A 15 second English speech clip, 16 kHz, mono, 16-bit PCM. Regenerate it with `uv run python scripts/make_fixture.py`. The output is byte-identical on every run.

- Source: LibriVox recording "The Gettysburg Address", hosted on the Internet Archive.
- Source URL: https://archive.org/download/gettysburg_address_librivox/gettysburg_address_lincoln.mp3
- Item page: https://archive.org/details/gettysburg_address_librivox
- Source SHA-256: `33e3cd5ac877db1cb08d1f4e2d75d120d7d1760a14da8c2c79435dc3383bd9b8`
- License: public domain. LibriVox releases its recordings to the public domain, and the Internet Archive item lists https://creativecommons.org/licenses/publicdomain/. The text is Abraham Lincoln's 1863 address.
- Cut: 15 seconds starting at 5 seconds into the source.

Large media (`*.mp4`, `*.mkv`) and models (`*.gguf`, `*.bin`) never go in the repo.

## en_15s.words.json

Word timestamps that CrispASR (Qwen3-ASR with the forced aligner) produced for `en_15s.wav`, taken from the P01 run `crispasr-en_15s-r1`. One object per ASR segment, with `words` as `text`, `start_ms`, `end_ms`. `tests/test_segmenter.py` and `scripts/check_cues.py` read it. The text is the LibriVox outro, spoken at the start of the clip.

## en_15s.probs.json

The silero-vad v6.2.3 speech probability for each 32 ms frame of `en_15s.wav`, rounded to 4 decimals, from `frame_probs` on the pinned ONNX model. `tests/test_vad.py` compares fresh output with it, which pins the context window, the gain, and the state handling. Regenerate it only when the model pin changes.

## engines/

Recorded engine output for `tests/test_engines.py`. `whisper_15s.json` and `crispasr_15s.json` are the `-ojf` files that whisper.cpp b5454 (large-v3-turbo, `-ng`) and CrispASR v0.8.49 (Qwen3-ASR-1.7B q8_0 with the Qwen3 aligner, `-ng`) wrote for `en_15s.wav`, with the local model and system strings blanked. `whisper_stderr.txt` and `crispasr_stderr.txt` are the lines the same runs printed to stderr that the progress parser reads, for two input files, with the local paths cut to file names. `fake_cli.py` replays them in place of the engine binary.

## engines/whisper_ja_15s.json

The first three segments of whisper.cpp `large-v3-turbo` `-l ja` raw output (`-ojf`) for the CEDEC 2026 Perforce P4 talk, taken from the P22 run `whisper-cedec-chunks-ja`. Only the three segments are kept, with their tokens and offsets, plus the `[_BEG_]` and `[_TT_]` marker tokens whisper writes. `tests/test_japanese.py` reads it to check that Japanese tokens are not merged into one word.
