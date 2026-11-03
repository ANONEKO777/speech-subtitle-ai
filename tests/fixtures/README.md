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
