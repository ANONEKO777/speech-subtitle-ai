from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "backend" / "core" / "subtitle_io.py"
MODEL = ROOT / "backend" / "core" / "model.py"


@dataclass(frozen=True)
class Mutation:
    name: str
    path: Path
    old: str
    new: str


MUTATIONS = [
    Mutation(
        "duplicate-id check removed from every reader",
        TARGET,
        "    return _check_unique_ids(cues)\n\n\ndef _blocks",
        "    return cues\n\n\ndef _blocks",
    ),
    Mutation(
        "write_text_file writes the target directly (non-atomic)",
        TARGET,
        "            os.replace(src, dst)\n",
        "            dst.write_bytes(src.read_bytes())\n",
    ),
    Mutation(
        "write_text_file skips fsync",
        TARGET,
        "            os.fsync(handle.fileno())\n",
        "            pass\n",
    ),
    Mutation(
        "write_text_file never retries a denied replace",
        TARGET,
        "            if delay is None:\n",
        "            if True:\n",
    ),
    Mutation(
        "SRT/VTT seconds >= 60 accepted",
        TARGET,
        "if int(minutes) >= 60 or int(seconds) >= 60:",
        "if int(minutes) >= 60:",
    ),
    Mutation(
        "ASS Format line may lack Start, End or Text",
        TARGET,
        '            missing = {"Start", "End", "Text"} - columns.keys()\n',
        "            missing = set[str]()\n",
    ),
    Mutation(
        "subs.json schema_version true accepted as 1",
        TARGET,
        "if type(version) is not int or version != SUBS_SCHEMA_VERSION:",
        "if version != SUBS_SCHEMA_VERSION:",
    ),
    Mutation(
        "timing line matched with search instead of fullmatch",
        TARGET,
        "_TIMING.fullmatch(",
        "_TIMING.search(",
    ),
    Mutation(
        "ASS time matched with search instead of fullmatch",
        TARGET,
        "_ASS_TIME.fullmatch(",
        "_ASS_TIME.search(",
    ),
    Mutation(
        "VTT &amp; unescaped first, so references decode twice",
        TARGET,
        "return _HTML_CHAR_REF.sub(lambda ref: html.unescape(ref.group()), untagged).strip()",
        'return html.unescape(untagged.replace("&amp;", "&")).strip()',
    ),
    Mutation(
        "VTT bare ampersand decoded like a reference",
        TARGET,
        "return _HTML_CHAR_REF.sub(lambda ref: html.unescape(ref.group()), untagged).strip()",
        "return html.unescape(untagged).strip()",
    ),
    Mutation(
        "VTT strips every tag-like span",
        TARGET,
        'r"</(?:c|i|b|u|ruby|rt|v|lang)>"',
        'r"</?[^>]*>"',
    ),
    Mutation(
        "fallback cue id is the cue position",
        TARGET,
        "next(free) if cue_id is None else cue_id,",
        "len(cues) + 1 if cue_id is None else cue_id,",
    ),
    Mutation(
        "ASS backslash before N, n or h written bare",
        TARGET,
        "text = _ASS_BACKSLASH_HAZARD.sub(lambda m: m.group() + _ASS_JOINER, text)",
        "pass",
    ),
    Mutation(
        "render_srt accepts duplicate ids",
        TARGET,
        "for cue in _check_unique_ids(list(cues))\n    ).removesuffix",
        "for cue in cues\n    ).removesuffix",
    ),
    Mutation(
        "Cue accepts padded text lines",
        MODEL,
        "any(line != line.strip() or not line for line in text.split",
        "any(not line.strip() for line in text.split",
    ),
    Mutation(
        "JSON strings accept lone surrogates",
        TARGET,
        '        value.encode("utf-8")\n',
        "        pass\n",
    ),
]


def killing_tests() -> list[str] | None:
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--maxfail=50"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode == 0:
        return None
    return [line.split(" - ")[0] for line in run.stdout.splitlines() if line.startswith("FAILED ")]


def main() -> int:
    originals = {path: path.read_bytes() for path in {m.path for m in MUTATIONS}}
    survivors = 0
    try:
        for mutation in MUTATIONS:
            source = originals[mutation.path].decode("utf-8")
            if source.count(mutation.old) != 1:
                print(f"STALE     {mutation.name}: anchor text not found exactly once")
                survivors += 1
                continue
            mutation.path.write_bytes(source.replace(mutation.old, mutation.new).encode("utf-8"))
            failed = killing_tests()
            mutation.path.write_bytes(originals[mutation.path])
            if failed is None:
                print(f"SURVIVED  {mutation.name}")
                survivors += 1
            else:
                print(f"killed    {mutation.name} ({len(failed)} failing, e.g. {failed[0][7:]})")
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
    print(f"{len(MUTATIONS) - survivors}/{len(MUTATIONS)} mutations killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
