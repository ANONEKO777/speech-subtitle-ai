"""Z0 E2: how well do Simplified to Traditional converters keep characters and leave wording alone.

Run it once in each environment that holds converters (the packages are NOT dependencies of the
repository; the experiment installs them in scratch environments under `.work/zh-z0/`):

    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_convert.py run --out native.json
    .work/zh-z0/venv-reimpl/Scripts/python scripts/zh_z0_convert.py run --out reimpl.json
    uv run python scripts/zh_z0_convert.py report native.json reimpl.json

`run` measures every converter it can import:
- `opencc` (the official native wheel), `opencc_purepy` (pure Python), `zhconv_rs` (a Rust wheel)
  and `opencc` of `opencc-python-reimplemented` (pure Python, same module name, hence its own
  environment).
- Round trip: real Traditional text of the repository is made Simplified (`t2s`), converted back
  (`s2t`), and the characters that differ from the original are counted. Real text means files
  the repository holds in Traditional Chinese (Taiwan), found by their share of Simplified-only
  characters.
- Wording: a list of 40 Simplified mainland terms; how many each configuration turns into the
  Taiwan term (the plain configuration must turn none).
- Speed of one conversion of the whole corpus.
"""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile("[㐀-鿿]")
KANA = re.compile("[぀-ヿ]")
Convert = Callable[[str], str]

MAINLAND_TO_TAIWAN = {
    "软件": "軟體", "内存": "記憶體", "信息": "資訊", "鼠标": "滑鼠", "视频": "影片",
    "默认": "預設", "网络": "網路", "服务器": "伺服器", "程序": "程式", "数据库": "資料庫",
    "优化": "最佳化", "用户": "使用者", "文件": "檔案", "打印": "列印", "激光": "雷射",
    "出租车": "計程車", "土豆": "馬鈴薯", "酸奶": "優格", "公交车": "公車", "质量": "品質",
    "硬盘": "硬碟", "摄像头": "攝影機", "博客": "部落格", "兼容": "相容", "支持": "支援",
    "调用": "呼叫", "搜索": "搜尋", "反馈": "回饋", "接口": "介面", "创建": "建立",
    "访问": "存取", "存储": "儲存", "数据": "資料", "源代码": "原始碼", "插件": "外掛",
    "打车": "叫車", "地铁": "捷運", "冰箱": "冰箱", "宇航员": "太空人", "手机": "手機",
}  # fmt: skip
"""Mainland wording, with the Taiwan term that a wording-changing configuration may give. `冰箱`
and `手机` are the same in both, so a converter that changes them is wrong; they are the control."""

AMBIGUOUS = "发后干里面布只台范复制志获钟周云向系冲松征占"
"""Simplified characters that stand for more than one Traditional character (发 is 發 or 髮,
后 is 後 or 后, 干 is 乾, 幹 or 干, 里 is 裡, 裏 or 里, 面 is 面 or 麵, 布 is 布 or 佈, 只 is 只 or
隻, 台 is 台, 臺, 檯 or 颱, ...)."""


def corpus() -> tuple[list[tuple[str, str]], dict[str, int]]:
    """The repository's own Traditional Chinese (Taiwan) text: file, text. Lines with kana (Japanese
    quotations) or with a character only Simplified writes are left out; a file counts when 300 or
    more Han characters remain."""
    sys.path.insert(0, str(ROOT))
    from backend.core.zh_tw import SIMPLIFIED_ONLY

    found: list[tuple[str, str]] = []
    skipped = {"lines_japanese": 0, "lines_simplified": 0, "files_short": 0}
    paths = [
        *sorted(ROOT.glob("*.md")),
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "tests").rglob("zh-TW.srt")),
    ]
    for path in paths:
        kept: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if KANA.search(line):
                skipped["lines_japanese"] += 1
            elif any(c in SIMPLIFIED_ONLY for c in line):
                skipped["lines_simplified"] += 1
            else:
                kept.append(line)
        text = "\n".join(kept)
        if len(HAN.findall(text)) < 300:
            skipped["files_short"] += 1
            continue
        found.append((str(path.relative_to(ROOT)).replace("\\", "/"), text))
    return found, skipped


def converters() -> dict[str, Convert]:
    """Every conversion this environment can do, under the name `<package>:<config>`."""
    out: dict[str, Convert] = {}

    def add(label: str, module: str, configs: list[str], attribute: str = "OpenCC") -> None:
        try:
            mod = importlib.import_module(module)
        except ImportError:
            return
        for config in configs:
            try:
                made = getattr(mod, attribute)(config)
            except Exception:  # noqa: BLE001 - a missing config is reported by its absence
                continue
            out[f"{label}:{config}"] = cast("Convert", made.convert)

    configs = ["s2t", "s2tw", "s2twp", "s2hk", "t2s", "tw2s", "hk2s", "tw2sp"]
    add("opencc", "opencc", configs)
    add("opencc-purepy", "opencc_purepy", configs)
    try:
        zhconv_rs = cast("Any", importlib.import_module("zhconv_rs"))
        for variant in ("zh-hans", "zh-hant", "zh-tw", "zh-hk", "zh-cn"):
            out[f"zhconv-rs:{variant}"] = lambda t, v=variant: cast("str", zhconv_rs.zhconv(t, v))
    except ImportError:
        pass
    return out


def hanzi_only(text: str) -> str:
    return "".join(HAN.findall(text))


def edit_pairs(a: str, b: str) -> list[tuple[str, str]]:
    """The (original, converted) character pairs where two texts of the same Han characters
    differ, by a standard alignment."""
    import difflib

    pairs: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if i2 - i1 == j2 - j1:
            pairs += [(a[i1 + k], b[j1 + k]) for k in range(i2 - i1)]
        else:
            pairs.append((a[i1:i2], b[j1:j2]))
    return pairs


def run(out: Path) -> None:
    texts, skipped = corpus()
    whole = "\n".join(text for _, text in texts)
    result: dict[str, Any] = {
        "corpus": [{"file": f, "han": len(HAN.findall(t))} for f, t in texts],
        "corpus_han": len(HAN.findall(whole)),
        "skipped": skipped,
        "converters": {},
    }
    table = converters()
    to_simplified = {
        name: fn
        for name, fn in table.items()
        if name.endswith(":t2s") or name.endswith(":zh-hans") or name.endswith(":zh-cn")
    }
    for name, fn in table.items():
        if name in to_simplified or name.endswith(("tw2s", "hk2s", "tw2sp")):
            continue
        row: dict[str, Any] = {}
        package = name.split(":")[0]
        t2s = table.get(f"{package}:t2s") or table.get(f"{package}:zh-hans")
        if t2s is not None:
            started = time.perf_counter()
            simplified = t2s(whole)
            row["t2s_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            back = fn(simplified)
            row["seconds"] = time.perf_counter() - started
            row["chars_per_second"] = len(simplified) / max(row["seconds"], 1e-9)
            original, restored = hanzi_only(whole), hanzi_only(back)
            pairs = edit_pairs(original, restored)
            row["han"] = len(original)
            row["han_after"] = len(restored)
            row["mismatches"] = len(pairs)
            row["error_rate"] = len(pairs) / max(len(original), 1)
            row["top_confusions"] = [[a, b, n] for (a, b), n in Counter(pairs).most_common(25)]
            ambiguous_total = sum(1 for c in simplified if c in AMBIGUOUS)
            ambiguous_wrong = sum(1 for a, _ in pairs if t2s(a) in AMBIGUOUS)
            row["ambiguous_chars"] = ambiguous_total
            row["ambiguous_wrong"] = ambiguous_wrong
        words = {simple: fn(simple) for simple in MAINLAND_TO_TAIWAN}
        row["wording_to_taiwan"] = sum(
            1 for s, taiwan in MAINLAND_TO_TAIWAN.items() if words[s] == taiwan and s != taiwan
        )
        row["wording_examples"] = {
            s: words[s] for s in ("软件", "内存", "信息", "鼠标", "视频", "默认", "程序", "土豆")
        }
        row["control_unchanged_wrongly"] = sum(
            1 for s in ("冰箱", "手机") if words[s] != fn(s) or fn(s) not in (s, "冰箱", "手機")
        )
        row["sample"] = fn("我发现后面的头发里面很干，面包在布里。发展 干净 皇后 以后 软件")
        result["converters"][name] = row
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(result['converters'])} converters, {result['corpus_han']} Han chars")


def report(paths: list[Path]) -> None:
    merged: dict[str, Any] = {}
    corpus_info: dict[str, Any] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        corpus_info = data
        merged.update(data["converters"])
    print(
        f"corpus: {len(corpus_info['corpus'])} files, {corpus_info['corpus_han']} Han characters;"
        f" skipped {corpus_info['skipped']}"
    )
    print(
        "| converter | round-trip errors | rate | ambiguous chars wrong | wording to Taiwan (of 38) |"
    )
    print("|---|---|---|---|---|")
    for name, row in sorted(merged.items()):
        if "error_rate" not in row:
            continue
        print(
            f"| {name} | {row['mismatches']} / {row['han']} | {row['error_rate']:.2%} | "
            f"{row['ambiguous_wrong']} / {row['ambiguous_chars']} | {row['wording_to_taiwan']} |"
        )
    for name, row in sorted(merged.items()):
        if "top_confusions" in row and name.split(":")[1] in ("s2t", "s2tw", "zh-hant", "zh-tw"):
            top = ", ".join(f"{a}->{b} x{n}" for a, b, n in row["top_confusions"][:12])
            print(f"- {name}: {top}")
    print("\nspeed (characters per second of s2t on the corpus)")
    for name, row in sorted(merged.items()):
        if "chars_per_second" in row:
            print(f"- {name}: {row['chars_per_second']:,.0f}")
    print("\nsamples")
    for name, row in sorted(merged.items()):
        print(f"- {name}: {row['sample']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--out", type=Path, required=True)
    reporter = sub.add_parser("report")
    reporter.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    if args.cmd == "run":
        run(args.out)
    else:
        report(args.files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
