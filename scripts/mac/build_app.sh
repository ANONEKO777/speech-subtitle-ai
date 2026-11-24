#!/usr/bin/env bash
# Build the Mac app (Video Subtitle Translator.app) and its disk image on this Mac.
#
# Run it from anywhere:   bash scripts/mac/build_app.sh
#
# Steps: the backend as a PyInstaller folder (installer/sidecar.spec), then `tauri build`, which
# builds the frontend first (beforeBuildCommand in app/src-tauri/tauri.conf.json) and packs the
# app and the dmg. The app is signed ad hoc (signingIdentity "-"): no Apple account is needed, and
# the app opens on this Mac and, after the approval steps in docs/MACOS.md, on another one.
# It needs no sudo and writes only under installer/build and app/src-tauri/target.
#
# ffmpeg is not packed: the app finds the Homebrew one (docs/MACOS.md).
# Not run by the author: this was written on Windows and checked with `bash -n` only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/installer/build"

fail() {
  echo "error: $*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 was not found: $2"
}

[ "$(uname -s)" = "Darwin" ] || fail "this script builds for macOS and this is $(uname -s)"
[ "$(uname -m)" = "arm64" ] || fail "an Apple-silicon Mac is needed; this one reports $(uname -m)"
xcode-select -p >/dev/null 2>&1 || fail "the Xcode command line tools are missing: run  xcode-select --install"
need node "install it with  brew install node"
need npm "install it with  brew install node"
need uv "install it with  brew install uv"
need cargo "install Rust from https://rustup.rs, then open a new terminal"

echo "1/4 Packing the backend with PyInstaller ..."
cd "$ROOT"
rm -rf "$BUILD/pyi" "$BUILD/pyi-work" "$BUILD/backend"
mkdir -p "$BUILD/backend"
uv sync --group build --locked
uv run --group build pyinstaller installer/sidecar.spec --noconfirm \
  --distpath "$BUILD/pyi" --workpath "$BUILD/pyi-work"
[ -x "$BUILD/pyi/vst-backend/vst-backend" ] || fail "PyInstaller did not produce vst-backend/vst-backend"
cp -a "$BUILD/pyi/vst-backend/." "$BUILD/backend/"

echo "2/4 Installing the frontend packages ..."
npm --prefix "$ROOT/app" ci

echo "3/4 Building the frontend and the app (the first run compiles Rust and takes a while) ..."
cd "$ROOT/app"
npx tauri build --bundles app,dmg --config ../installer/tauri.bundle.mac.conf.json

BUNDLE="$ROOT/app/src-tauri/target/release/bundle"
[ -d "$BUNDLE/macos" ] || fail "tauri build left no $BUNDLE/macos folder; read its output above"
[ -d "$BUNDLE/dmg" ] || fail "tauri build left no $BUNDLE/dmg folder; read its output above"
APP="$(find "$BUNDLE/macos" -maxdepth 1 -name '*.app' | head -n 1)"
DMG="$(find "$BUNDLE/dmg" -maxdepth 1 -name '*.dmg' | head -n 1)"
[ -n "$APP" ] || fail "no .app was produced under $BUNDLE/macos"
[ -n "$DMG" ] || fail "no .dmg was produced under $BUNDLE/dmg"

echo "4/4 Checking the signature ..."
if codesign --verify --deep --strict --verbose=2 "$APP"; then
  echo "signature: valid (ad hoc)"
else
  echo "warning: codesign does not accept the app as built; see docs/MACOS.md, 'If the app will not open'" >&2
fi

echo
echo "App: $APP"
echo "Disk image: $DMG"
