"""The Mac preflight script (step 0 of docs/MACOS.md), run against fake Mac tools.

The script reads the machine with uname, sw_vers, sysctl, df and the build tools. Each scenario
puts small fake programs of those names on PATH and runs the real script with nothing else on PATH,
so the answers do not depend on this machine. Skipped when no working bash exists."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mac" / "preflight.sh"
DOC = ROOT / "docs" / "MACOS.md"


def working_bash() -> str | None:
    found = shutil.which("bash")
    if found is None:
        return None
    probe = 'd="$(mktemp -d)" && [ -d "$d" ] && command -v awk sed head dirname grep && rm -rf "$d"'
    if subprocess.run([found, "-c", probe], capture_output=True).returncode:
        return None
    return found


BASH = working_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="no working bash on this machine")

NO_PROBLEMS = "預檢完成，沒有發現問題"

GOOD: dict[str, str] = {
    "uname": 'case "$1" in -s) echo Darwin;; -m) echo arm64;; esac',
    "sw_vers": (
        "printf 'ProductName:\\t\\tmacOS\\nProductVersion:\\t\\t15.1\\nBuildVersion:\\t\\t24B83\\n'"
    ),
    "sysctl": (
        'case "$2" in hw.memsize) echo 38654705664;; '
        "machdep.cpu.brand_string) echo 'Apple M3 Pro';; hw.optional.arm64) echo 1;; esac"
    ),
    "df": "printf 'Filesystem 1G-blocks Used Available Capacity Mounted on\\n"
    "/dev/disk3s5 460 300 160 66%% /System/Volumes/Data\\n'",
    "xcode-select": "echo /Library/Developer/CommandLineTools",
    "git": "echo 'git version 2.39.5 (Apple Git-154)'",
    "cmake": "echo 'cmake version 3.31.2'",
    "brew": "echo 'Homebrew 4.4.9'",
    "uv": "echo 'uv 0.5.10'",
    "node": "echo v22.12.0",
    "cargo": "echo 'cargo 1.83.0'",
    "ffmpeg": (
        'case "$*" in *-encoders*) echo " V....D h264_videotoolbox VideoToolbox H.264 Encoder";; '
        "*) echo 'ffmpeg version 7.1.1';; esac"
    ),
    "ffprobe": "echo 'ffprobe version 7.1.1'",
    "whisper-cli": "echo whisper",
}


def without(*names: str) -> dict[str, str]:
    return {name: body for name, body in GOOD.items() if name not in names}


def run_preflight(shims: dict[str, str], data_files: tuple[str, ...] = ()) -> tuple[int, str, str]:
    """Runs the script under bash with only `shims` (and awk, sed, head, dirname, grep) on PATH.

    Returns its exit code, its output, and what it left in the home folder, the data folder and
    the temporary folder beside them (nothing, for a read-only script)."""
    assert BASH is not None
    parts = [
        "set -e",
        'd="$(mktemp -d)"',
        "trap 'rm -rf \"$d\"' EXIT",
        'mkdir "$d/bin" "$d/home"',
        'cat > "$d/preflight.sh"',
        'for t in awk sed head dirname grep; do p="$(command -v $t)"; '
        'printf \'#!/bin/sh\\nexec "%s" "$@"\\n\' "$p" > "$d/bin/$t"; chmod +x "$d/bin/$t"; done',
    ]
    for name, body in shims.items():
        parts.append(f"cat > \"$d/bin/{name}\" <<'SHIM'\n#!/bin/sh\n{body}\nSHIM")
        parts.append(f'chmod +x "$d/bin/{name}"')
    for rel in data_files:
        parts.append(f'mkdir -p "$(dirname "$d/home/data/{rel}")"; touch "$d/home/data/{rel}"')
    parts += [
        'before="$(cd "$d" && find . | sort | tr "\\n" " ")"',
        "set +e",
        'PATH="$d/bin" HOME="$d/home" VST_USER_DATA="$d/home/data" '
        'VST_HOMEBREW_DIRS="$d/no-homebrew" "$BASH" "$d/preflight.sh"',
        "code=$?",
        'after="$(cd "$d" && find . | sort | tr "\\n" " ")"',
        'echo "@@code=$code"',
        '[ "$before" = "$after" ] || echo "@@changed: $after"',
        "exit 0",
    ]
    done = subprocess.run(
        [BASH, "-c", "\n".join(parts)],
        input=SCRIPT.read_bytes().replace(b"\r\n", b"\n"),
        capture_output=True,
        check=False,
    )
    text = done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    body, _, tail = text.rpartition("@@code=")
    code, _, extra = tail.partition("\n")
    return int(code), body, extra


@needs_bash
def test_a_mac_with_everything_installed_reports_each_fact_and_no_problem() -> None:
    code, out, changed = run_preflight(GOOD)

    assert code == 0
    assert out.rstrip().splitlines()[-1] == NO_PROBLEMS
    for fact in (
        "uname -m: arm64",
        "ProductVersion:\t\t15.1",
        "hw.memsize: 38654705664 (36 GB)",
        "machdep.cpu.brand_string: Apple M3 Pro",
        "可用磁碟空間: 160 GB",
        "xcode-select -p: /Library/Developer/CommandLineTools",
        "git: git version 2.39.5",
        "cmake: cmake version 3.31.2",
        "brew: Homebrew 4.4.9",
        "uv: uv 0.5.10",
        "node: v22.12.0",
        "cargo: cargo 1.83.0",
        "ffmpeg: ffmpeg version 7.1.1",
        "ffmpeg h264_videotoolbox: 有",
        "ffprobe: ffprobe version 7.1.1",
        "whisper-cli: ",
        "資料夾: ",
    ):
        assert fact in out
    assert "提醒" not in out
    assert "@@changed" not in changed


@needs_bash
def test_a_mac_missing_cmake_and_brew_gets_one_plain_line_per_problem_and_a_count() -> None:
    code, out, _ = run_preflight(without("cmake", "brew"))

    assert code == 0
    assert "cmake: 找不到" in out
    assert "缺少 cmake：請執行 brew install cmake" in out
    assert "缺少 brew：請執行 安裝 Homebrew（https://brew.sh）" in out
    assert out.rstrip().splitlines()[-1] == "預檢完成，發現 2 個問題"
    assert NO_PROBLEMS not in out


@needs_bash
def test_a_missing_whisper_cli_is_a_reminder_that_does_not_count_as_a_problem() -> None:
    code, out, _ = run_preflight(without("whisper-cli"))

    assert code == 0
    assert "whisper-cli: 還沒有" in out
    assert "提醒：還沒有 whisper-cli" in out
    assert "scripts/mac/build_whisper_cli.sh" in out
    assert out.rstrip().splitlines()[-1] == NO_PROBLEMS


@needs_bash
def test_whisper_cli_in_the_runtimes_folder_is_found_there() -> None:
    own = "runtimes/whispercpp-b5454-macos-metal/whisper-cli"
    _, out, _ = run_preflight(without("whisper-cli"), data_files=(own,))

    assert own in out
    assert "提醒" not in out


@needs_bash
def test_an_intel_mac_is_stopped_with_one_plain_sentence() -> None:
    shims = GOOD | {
        "uname": 'case "$1" in -s) echo Darwin;; -m) echo x86_64;; esac',
        "sysctl": 'case "$2" in hw.optional.arm64) echo 0;; esac',
    }
    code, out, _ = run_preflight(shims)

    assert code == 1
    assert "需要 Apple 晶片（M1 或更新）的 Mac；這台回報 x86_64，已停止。" in out
    assert "預檢完成" not in out
    assert "cmake" not in out


@needs_bash
def test_an_apple_silicon_mac_in_a_rosetta_terminal_is_told_to_open_a_native_one() -> None:
    shims = GOOD | {"uname": 'case "$1" in -s) echo Darwin;; -m) echo x86_64;; esac'}
    code, out, _ = run_preflight(shims)

    assert code == 1
    assert "Rosetta" in out
    assert "已停止" in out


@needs_bash
def test_linux_is_stopped_before_anything_else_is_read() -> None:
    shims = GOOD | {"uname": 'case "$1" in -s) echo Linux;; -m) echo x86_64;; esac'}
    code, out, _ = run_preflight(shims)

    assert code == 1
    assert "這台是 Linux x86_64，已停止。" in out
    assert "預檢完成" not in out
    assert "hw.memsize" not in out


@needs_bash
def test_ffmpeg_without_the_videotoolbox_encoder_is_a_problem() -> None:
    shims = GOOD | {
        "ffmpeg": (
            'case "$*" in *-encoders*) echo " V....D libx264 x264";; *) echo "ffmpeg 7.1";; esac'
        )
    }
    _, out, _ = run_preflight(shims)

    assert "ffmpeg h264_videotoolbox: 沒有" in out
    assert "沒有 h264_videotoolbox 編碼器" in out
    assert out.rstrip().splitlines()[-1] == "預檢完成，發現 1 個問題"


@needs_bash
def test_without_the_command_line_tools_git_is_not_run() -> None:
    shims = GOOD | {
        "xcode-select": "exit 2",
        "git": 'echo ran >> "$HOME/git-was-run"; echo git version',
    }
    code, out, changed = run_preflight(shims)

    assert code == 0
    assert "缺少 Xcode 命令列工具：請執行 xcode-select --install" in out
    assert "git: 未檢查" in out
    assert "git-was-run" not in changed


@needs_bash
def test_a_nearly_full_disk_and_an_old_macos_are_problems() -> None:
    shims = GOOD | {
        "df": "printf 'Filesystem 1G-blocks Used Available Capacity Mounted on\\n"
        "/dev/disk3s5 460 450 6 99%% /System/Volumes/Data\\n'",
        "sw_vers": "printf 'ProductName:\\t\\tmacOS\\nProductVersion:\\t\\t12.7.6\\n'",
    }
    _, out, _ = run_preflight(shims)

    assert "磁碟空間不足：只剩 6 GB" in out
    assert "macOS 版本太舊（12.7.6）" in out
    assert out.rstrip().splitlines()[-1] == "預檢完成，發現 2 個問題"


@needs_bash
def test_a_df_that_prints_nothing_is_a_problem_not_a_crash() -> None:
    code, out, _ = run_preflight(GOOD | {"df": "exit 1"})

    assert code == 0
    assert "可用磁碟空間: 讀不到" in out
    assert out.rstrip().splitlines()[-1] == "預檢完成，發現 1 個問題"


def test_the_script_never_uses_sudo_or_writes_anything() -> None:

    code = [
        line.strip()
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert not [line for line in code if re.search(r"\bsudo\b", line)]
    assert not [line for line in code if re.match(r"(cp|mv|mkdir|rm|chmod|touch|tee)\b", line)]
    assert not [line for line in code if re.search(r"(?<![-\d&])>\s*[^&/\s]", line)]


def test_the_script_has_unix_line_endings() -> None:
    assert b"\r" not in SCRIPT.read_bytes()


@needs_bash
def test_the_script_is_valid_shell() -> None:
    assert BASH is not None
    done = subprocess.run([BASH, "-n"], input=SCRIPT.read_bytes(), capture_output=True, check=False)

    assert done.returncode == 0, done.stderr.decode(errors="replace")


def test_the_page_makes_the_preflight_step_zero() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "scripts/mac/preflight.sh" in text
    assert text.index("scripts/mac/preflight.sh") < text.index("xcode-select --install")
