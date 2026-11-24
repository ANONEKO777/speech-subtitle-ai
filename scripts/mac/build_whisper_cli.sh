#!/usr/bin/env bash
# Build whisper-cli with Metal on this Mac and put it where the app looks for it.
#
# whisper.cpp publishes no macOS program, so the registry row for whisper on a Mac
# (whispercpp-b5454-macos-metal in backend/manager/registry.json) is built here, once.
# Run it from anywhere:   bash scripts/mac/build_whisper_cli.sh
#
# It needs the Xcode command line tools, git and cmake (see docs/MACOS.md). It needs no sudo and
# writes only to a temporary folder and to the runtimes folder of the app's data folder.
#
# Not run by the author: this was written on Windows and checked with `bash -n` only.
set -euo pipefail

RUNTIME_ID="whispercpp-b5454-macos-metal"
TAG="${WHISPER_CPP_TAG:-b5454}"
REPO_URL="https://github.com/ggml-org/whisper.cpp"
DATA_DIR="${VST_USER_DATA:-$HOME/Library/Application Support/video-subtitle-translator}"
DEST_DIR="$DATA_DIR/runtimes/$RUNTIME_ID"
DEST="$DEST_DIR/whisper-cli"

fail() {
  echo "error: $*" >&2
  exit 1
}

[ "$(uname -s)" = "Darwin" ] || fail "this script builds for macOS and this is $(uname -s)"
[ "$(uname -m)" = "arm64" ] || fail "an Apple-silicon Mac is needed; this one reports $(uname -m)"
command -v git >/dev/null 2>&1 || fail "git was not found: run  xcode-select --install"
command -v xcrun >/dev/null 2>&1 || fail "the Xcode command line tools are missing: run  xcode-select --install"
command -v cmake >/dev/null 2>&1 || fail "cmake was not found: run  brew install cmake"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/vst-whisper-build.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "Cloning whisper.cpp $TAG ..."
git clone --quiet --depth 1 --branch "$TAG" "$REPO_URL" "$WORK/src"

echo "Configuring (Metal on, shaders embedded, static) ..."
cmake -S "$WORK/src" -B "$WORK/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=ON \
  -DGGML_METAL_EMBED_LIBRARY=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DWHISPER_BUILD_TESTS=OFF \
  -DWHISPER_BUILD_EXAMPLES=ON

echo "Building whisper-cli (a few minutes) ..."
cmake --build "$WORK/build" --config Release --target whisper-cli -j "$(sysctl -n hw.ncpu)"

BUILT="$WORK/build/bin/whisper-cli"
[ -f "$BUILT" ] || BUILT="$WORK/build/bin/Release/whisper-cli"
[ -f "$BUILT" ] || fail "the build finished but whisper-cli is not in $WORK/build/bin"

mkdir -p "$DEST_DIR"
cp "$BUILT" "$DEST.new"
chmod 755 "$DEST.new"
mv -f "$DEST.new" "$DEST"

"$DEST" --help >/dev/null 2>&1 || fail "$DEST was copied but does not start"
echo "Done: $DEST"
