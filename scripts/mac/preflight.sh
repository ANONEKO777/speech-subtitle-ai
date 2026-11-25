#!/usr/bin/env bash
# Step 0 of docs/MACOS.md: look at this Mac and say what is missing, before anything is installed.
#
# Read-only: it needs no sudo, creates and changes nothing, and writes only to the terminal. It runs
# a version command for each tool it finds, and nothing else. Run it from anywhere:
#   bash scripts/mac/preflight.sh
# Copy the whole block it prints and send it back.
#
# Not run on a Mac by the author: it was written on Windows and tested with fake uname, sw_vers,
# sysctl and df programs (tests/test_macos_preflight.py).
set -u

RUNTIME_ID="whispercpp-b5454-macos-metal"
DATA_DIR="${VST_USER_DATA:-$HOME/Library/Application Support/video-subtitle-translator}"
MIN_FREE_GB=20
# The two folders the app also searches for ffmpeg and whisper-cli (backend/core/audio.py).
# VST_HOMEBREW_DIRS replaces them, for the tests.
HOMEBREW_DIRS="${VST_HOMEBREW_DIRS:-/opt/homebrew/bin /usr/local/bin}"

SYSTEM="$(uname -s 2>/dev/null)"
ARCH="$(uname -m 2>/dev/null)"

echo "=== Mac 預檢 ==="
echo "uname -m: $ARCH"
echo "uname -s: $SYSTEM"

if [ "$SYSTEM" != "Darwin" ]; then
  echo "這支預檢只能在 Apple 晶片的 Mac 上執行；這台是 ${SYSTEM} ${ARCH}，已停止。"
  exit 1
fi

if [ "$ARCH" != "arm64" ]; then
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    echo "這是 Apple 晶片的 Mac，但終端機正以 Rosetta（x86_64）執行，已停止。"
    echo "請用原生的終端機重新開啟（在 Finder 的「終端機」資訊視窗取消勾選「使用 Rosetta 開啟」），再執行一次。"
  else
    echo "需要 Apple 晶片（M1 或更新）的 Mac；這台回報 ${ARCH}，已停止。"
  fi
  exit 1
fi

PROBLEMS=()
NOTES=()

problem() { PROBLEMS+=("$1"); }
note() { NOTES+=("$1"); }

first_line() { head -n 1; }

# A Homebrew program is only found by the build script and the app when its folder is on PATH
# (the app also looks in the Homebrew folders itself). Look there too, and say when PATH lacks it.
brew_dir_missing_from_path=""
for dir in $HOMEBREW_DIRS; do
  if [ -d "$dir" ]; then
    case ":$PATH:" in
      *":$dir:"*) ;;
      *) brew_dir_missing_from_path="$brew_dir_missing_from_path $dir" ;;
    esac
  fi
done
for dir in $HOMEBREW_DIRS; do PATH="$PATH:$dir"; done
if [ -n "$brew_dir_missing_from_path" ]; then
  problem "Homebrew 的資料夾不在 PATH 上（$brew_dir_missing_from_path ）：請執行 eval \"\$(/opt/homebrew/bin/brew shellenv)\"，再把同一行加進 ~/.zprofile，然後開新的終端機視窗"
fi

sw_vers_text="$(sw_vers 2>/dev/null)"
echo "sw_vers:"
echo "$sw_vers_text" | sed 's/^/  /'
macos_version="$(echo "$sw_vers_text" | sed -n 's/^ProductVersion:[[:space:]]*//p' | first_line)"
macos_major="${macos_version%%.*}"
case "$macos_major" in
  '' | *[!0-9]*) problem "讀不到 macOS 版本：請把上面 sw_vers 的輸出貼回來" ;;
  *) [ "$macos_major" -ge 13 ] || problem "macOS 版本太舊（${macos_version}）：預先編好的 llama.cpp 與 CrispASR 需要 macOS 13 或更新" ;;
esac

mem_bytes="$(sysctl -n hw.memsize 2>/dev/null)"
case "$mem_bytes" in
  '' | *[!0-9]*) echo "hw.memsize: 讀不到"; problem "讀不到記憶體大小：請把這份輸出貼回來" ;;
  *) echo "hw.memsize: $mem_bytes ($((mem_bytes / 1073741824)) GB)" ;;
esac

echo "machdep.cpu.brand_string: $(sysctl -n machdep.cpu.brand_string 2>/dev/null)"

echo "資料夾: $DATA_DIR"
probe="$DATA_DIR"
while [ ! -d "$probe" ] && [ "$probe" != "/" ] && [ -n "$probe" ]; do
  probe="$(dirname "$probe")"
done
free_gb="$(df -g "$probe" 2>/dev/null | awk 'NR==2 {print $4}')"
case "$free_gb" in
  '' | *[!0-9]*)
    echo "可用磁碟空間: 讀不到"
    problem "讀不到資料夾所在磁碟的可用空間：請把這份輸出貼回來"
    ;;
  *)
    echo "可用磁碟空間: $free_gb GB（在 $probe 所在的磁碟）"
    [ "$free_gb" -ge "$MIN_FREE_GB" ] || problem "磁碟空間不足：只剩 $free_gb GB，模型與建置至少要預留 $MIN_FREE_GB GB，請先清出空間"
    ;;
esac

# `git` and the other Xcode tools in /usr/bin are stubs that open an install window when the
# command line tools are missing, so none of them is run until xcode-select finds the tools.
if clt_path="$(xcode-select -p 2>/dev/null)" && [ -n "$clt_path" ]; then
  echo "xcode-select -p: $clt_path"
  have_clt=1
else
  echo "xcode-select -p: 未安裝"
  problem "缺少 Xcode 命令列工具：請執行 xcode-select --install"
  have_clt=0
fi

check() {
  # check <command> <how to install> <version command...>
  local name="$1" fix="$2"
  shift 2
  if command -v "$name" >/dev/null 2>&1; then
    echo "$name: $("$@" 2>&1 | first_line)"
    return 0
  fi
  echo "$name: 找不到"
  problem "缺少 ${name}：請執行 ${fix}"
  return 1
}

if [ "$have_clt" = 1 ]; then
  check git "xcode-select --install" git --version
else
  echo "git: 未檢查（要先裝命令列工具）"
fi
check cmake "brew install cmake" cmake --version
check brew "安裝 Homebrew（https://brew.sh），再執行 brew install cmake ffmpeg uv" brew --version
check uv "brew install uv" uv --version
check node "brew install node（只有建置視窗版需要）" node --version
check cargo "安裝 Rust（curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh，只有建置視窗版需要；裝完請開新的終端機視窗）" cargo --version
if check ffmpeg "brew install ffmpeg" ffmpeg -version; then
  if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
    echo "ffmpeg h264_videotoolbox: 有"
  else
    echo "ffmpeg h264_videotoolbox: 沒有"
    problem "這個 ffmpeg 沒有 h264_videotoolbox 編碼器，燒進字幕會失敗：請執行 brew install ffmpeg，並確認用的是 Homebrew 的那一個"
  fi
else
  echo "ffmpeg h264_videotoolbox: 未檢查"
fi
check ffprobe "brew install ffmpeg" ffprobe -version

whisper=""
own="$DATA_DIR/runtimes/$RUNTIME_ID/whisper-cli"
if [ -f "$own" ]; then
  whisper="$own"
elif found="$(command -v whisper-cli 2>/dev/null)" && [ -n "$found" ]; then
  whisper="$found"
else
  for dir in $HOMEBREW_DIRS; do
    [ -f "$dir/whisper-cli" ] && whisper="$dir/whisper-cli" && break
  done
fi
if [ -n "$whisper" ]; then
  echo "whisper-cli: $whisper"
else
  echo "whisper-cli: 還沒有"
  note "還沒有 whisper-cli：這是正常的，到 docs/MACOS.md 的步驟 4 執行 bash scripts/mac/build_whisper_cli.sh 就會建好"
fi

echo
echo "=== 結果 ==="
for line in "${NOTES[@]+"${NOTES[@]}"}"; do
  echo "提醒：$line"
done
for line in "${PROBLEMS[@]+"${PROBLEMS[@]}"}"; do
  echo "$line"
done
if [ "${#PROBLEMS[@]}" -eq 0 ]; then
  echo "預檢完成，沒有發現問題"
else
  echo "預檢完成，發現 ${#PROBLEMS[@]} 個問題"
fi
exit 0
