from __future__ import annotations

import html
import itertools
import json
import os
import re
import time
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal, NamedTuple, cast

from backend.core.languages import DEFAULT_CODE, UnknownLanguage, Wrap
from backend.core.languages import get as get_language
from backend.core.model import (
    Cue,
    FormatError,
    Project,
    Step,
    StepState,
    StepStatus,
)

MonoLang = Literal["en", "zh"]
RenderLang = Literal["en", "zh", "bilingual"]

SUBS_SCHEMA_VERSION = 1

_REPLACE_DELAYS_S = (0.02, 0.04, 0.08, 0.16, 0.32)

_TIMING = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})(?:\s.*)?"
)
_ASS_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})")
_VTT_TAG = re.compile(
    r"</(?:c|i|b|u|ruby|rt|v|lang)>"
    r"|<(?:c|i|b|u|ruby|rt)(?:\.[^\s.>]+)*>"
    r"|<(?:v|lang)(?:\.[^\s.>]+)*(?:[ \t][^>]*)?>"
    r"|<(?:\d+:)?\d{2}:\d{2}\.\d{3}>"
)
_HTML_CHAR_REF = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_LINE_BREAK = re.compile(r"\r\n|[\r\n]")
_ASS_JOINER = "⁠"
_ASS_BACKSLASH_HAZARD = re.compile(rf"\\(?=[Nnh{_ASS_JOINER}])")
_ASS_TOKEN = re.compile(rf"\\N|\\n|\\\{{|\\\}}|\\{_ASS_JOINER}|\{{[^}}]*\}}")
_ASS_EN_MARK = "{\\rEn}"
_ASS_SOFT_BREAK = "\\N{\\q0}"
ASS_ZH_LINE_COLUMNS = 40
_EXTRA_LINES = 3
_NARROW = ("N", "Na", "A")
_THAI_LEADING_VOWELS = "เแโใไ"
_ASS_OPENERS = "(（[【「『《〈“‘"
_ASS_CLOSERS = "，。？！、；：)）]】」』》〉”’…"
_ASS_CLAUSE_END = "，。？！、；："

_ASS_STYLE_FIELDS = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
    "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
_ASS_STYLE_TAIL = (
    "&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2.5,0,2,60,60,40,1"
)
_ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: {_ASS_STYLE_FIELDS}
Style: Zh,Microsoft JhengHei,56,{_ASS_STYLE_TAIL}
Style: En,Arial,40,{_ASS_STYLE_TAIL}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def read_text_file(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FormatError(f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from exc


def _replace_with_retry(src: Path, dst: Path) -> None:
    for delay in (*_REPLACE_DELAYS_S, None):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if dst.is_dir():
                raise PermissionError(exc.errno, f"cannot replace {dst}: it is a folder") from exc
            if dst.exists() and not os.access(dst, os.W_OK):
                raise PermissionError(exc.errno, f"cannot replace {dst}: it is read-only") from exc
            if delay is None:
                raise PermissionError(
                    exc.errno, f"cannot replace {dst}: it is open in another program"
                ) from exc
            time.sleep(delay)


def write_text_file(path: Path, text: str) -> None:
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FormatError(f"{path}: text is not valid UTF-8 ({exc.reason})") from exc
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            exc.errno, f"cannot write {path}: the folder {path.parent} does not exist"
        ) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _lines(text: str) -> list[str]:
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _cue_text(cue: Cue, lang: RenderLang) -> str:
    if lang == "en":
        return cue.en
    if lang == "zh":
        return cue.zh
    return "\n".join(part for part in (cue.zh, cue.en) if part)


def _timestamp(ms: int, sep: str) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def _timing_ms(match: re.Match[str], offset: int) -> int:
    hours, minutes, seconds, millis = match.group(offset, offset + 1, offset + 2, offset + 3)
    if int(minutes) >= 60 or int(seconds) >= 60:
        raise ValueError("minutes and seconds must be below 60")
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def _check_unique_ids(cues: list[Cue]) -> list[Cue]:
    seen: set[int] = set()
    for cue in cues:
        if cue.id in seen:
            raise FormatError(f"duplicate cue id {cue.id}")
        seen.add(cue.id)
    return cues


class _RawCue(NamedTuple):
    lineno: int
    ident: str
    start_ms: int
    end_ms: int
    en: str
    zh: str


def _build_cues(rows: list[_RawCue]) -> list[Cue]:
    explicit = [
        int(row.ident) if row.ident.isascii() and row.ident.isdigit() else None for row in rows
    ]
    taken = {i for i in explicit if i is not None}
    free = (n for n in itertools.count(1) if n not in taken)
    cues: list[Cue] = []
    for row, cue_id in zip(rows, explicit, strict=True):
        try:
            cues.append(
                Cue(
                    next(free) if cue_id is None else cue_id,
                    row.start_ms,
                    row.end_ms,
                    row.en,
                    row.zh,
                )
            )
        except ValueError as exc:
            raise FormatError(f"line {row.lineno}: {exc}") from exc
    return _check_unique_ids(cues)


def _blocks(lines: list[str]) -> Iterable[tuple[int, list[str]]]:
    start = 0
    block: list[str] = []
    for index, line in enumerate(lines):
        if line.strip():
            if not block:
                start = index + 1
            block.append(line.strip())
        elif block:
            yield start, block
            block = []
    if block:
        yield start, block


def _parse_timed_blocks(
    blocks: Iterable[tuple[int, list[str]]], lang: MonoLang, *, vtt: bool
) -> list[Cue]:
    rows: list[_RawCue] = []
    for lineno, block in blocks:
        head = 0 if "-->" in block[0] else 1
        match = _TIMING.fullmatch(block[head]) if head < len(block) else None
        if match is None:
            raise FormatError(
                f"line {lineno}: expected a timing line like 00:00:01,000 --> 00:00:02,000"
            )
        body = block[head + 1 :]
        if vtt:
            body = [part for line in body for part in _vtt_unescape(line)]
        text = "\n".join(body)
        try:
            start_ms, end_ms = _timing_ms(match, 1), _timing_ms(match, 5)
        except ValueError as exc:
            raise FormatError(f"line {lineno}: {exc}") from exc
        rows.append(
            _RawCue(
                lineno,
                block[0] if head else "",
                start_ms,
                end_ms,
                text if lang == "en" else "",
                text if lang == "zh" else "",
            )
        )
    return _build_cues(rows)


def render_srt(cues: Iterable[Cue], lang: RenderLang) -> str:
    return "".join(
        f"{cue.id}\n{_timestamp(cue.start_ms, ',')} --> {_timestamp(cue.end_ms, ',')}\n"
        f"{_cue_text(cue, lang)}\n\n"
        for cue in _check_unique_ids(list(cues))
    ).removesuffix("\n")


def parse_srt(text: str, lang: MonoLang) -> list[Cue]:
    return _parse_timed_blocks(_blocks(_lines(text)), lang, vtt=False)


def _vtt_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _vtt_unescape(line: str) -> list[str]:
    untagged = _VTT_TAG.sub("", line)
    decoded = _HTML_CHAR_REF.sub(lambda ref: html.unescape(ref.group()), untagged)
    return [part for part in map(str.strip, _LINE_BREAK.split(decoded)) if part]


def render_vtt(cues: Iterable[Cue], lang: RenderLang) -> str:
    body = "".join(
        f"{cue.id}\n{_timestamp(cue.start_ms, '.')} --> {_timestamp(cue.end_ms, '.')}\n"
        f"{_vtt_escape(_cue_text(cue, lang))}\n\n"
        for cue in _check_unique_ids(list(cues))
    )
    return "WEBVTT\n\n" + body.removesuffix("\n") if body else "WEBVTT\n"


def parse_vtt(text: str, lang: MonoLang) -> list[Cue]:
    blocks = iter(_blocks(_lines(text)))
    header = next(blocks, None)
    if header is None or not re.match(r"WEBVTT(?:[ \t]|$)", header[1][0]):
        raise FormatError("line 1: a WebVTT file must start with WEBVTT")
    cue_blocks = (
        b for b in blocks if b[1][0].split(maxsplit=1)[0] not in ("NOTE", "STYLE", "REGION")
    )
    return _parse_timed_blocks(cue_blocks, lang, vtt=True)


def _ass_time(ms: int) -> str:
    centis = (ms + 5) // 10
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6000)
    seconds, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _columns(char: str) -> int:
    """Display columns: a full-width character is two, a combining mark none."""
    if unicodedata.category(char) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


def _in_a_word(char: str) -> bool:
    """A letter or digit of a script written in words (Latin, Cyrillic, Greek). A Thai, kana or
    ideograph character is not: those scripts do not mark word ends with spaces."""
    return char.isalnum() and unicodedata.east_asian_width(char) in _NARROW and not _is_thai(char)


def _is_thai(char: str) -> bool:
    return "฀" <= char <= "๿"


def _can_break(before: str, after: str, wrap: Wrap) -> bool:
    """Whether a line may end with `before` and the next begin with `after`."""
    if before in _ASS_OPENERS or before == "\\" or after in _ASS_CLOSERS:
        return False
    match wrap:
        case Wrap.SPACES:
            return before.isspace() and not after.isspace()
        case Wrap.THAI:
            if before.isspace():
                return not after.isspace()
            if _in_a_word(before) and _in_a_word(after):
                return False
            if before in _THAI_LEADING_VOWELS:
                return False
            return after in _THAI_LEADING_VOWELS or "ก" <= after <= "ฮ" or not _is_thai(after)
        case Wrap.CJK:
            return not (_in_a_word(before) and _in_a_word(after))


def _cuts(line: str, limit: int, parts: int, wrap: Wrap) -> list[int]:
    """Up to `parts - 1` break indexes that split `line` into `parts` lines of at most `limit`
    columns, each at a break `_can_break` allows. A break prefers the end of a clause (a space,
    in Thai) that is not too close to the line start, then the point nearest an even split."""
    ends = list(itertools.accumulate(_columns(c) for c in line))
    total = ends[-1]
    clause_end = _ASS_CLAUSE_END + (" " if wrap is Wrap.THAI else "")
    cuts: list[int] = []
    start_col = 0
    for k in range(1, parts):
        ideal = start_col + (total - start_col) / (parts - k + 1)
        found: list[tuple[float, int, bool]] = []
        for i in range(cuts[-1] + 1 if cuts else 1, len(line)):
            col = ends[i - 1]
            if col - start_col > limit:
                break
            if total - col <= limit * (parts - k) and _can_break(line[i - 1], line[i], wrap):
                clause = line[i - 1] in clause_end and col - start_col >= limit // 4
                found.append((abs(col - ideal), i, clause))
        if not found:
            break
        near = [f for f in found if f[2] and f[0] <= limit // 2] or found
        cuts.append(min(near)[1])
        start_col = ends[cuts[-1] - 1]
    return cuts


def wrap_line(line: str, wrap: Wrap = Wrap.CJK, limit: int = ASS_ZH_LINE_COLUMNS) -> list[str]:
    """Split one long line into as few parts as fit `limit` display columns, where `wrap` says
    where a break may go. It never splits a word of a spaced script or a Thai grapheme cluster and
    never starts a line with closing punctuation. A line with no room to break is returned
    whole. Joining the parts gives `line`."""
    total = sum(_columns(c) for c in line)
    if total <= limit:
        return [line]
    least = -(-total // limit)
    cuts: list[int] = []
    for parts in range(least, least + _EXTRA_LINES + 1):
        cuts = _cuts(line, limit, parts, wrap)
        if len(cuts) == parts - 1:
            break
    else:
        cuts = _cuts(line, limit, least, wrap)
    bounds = [0, *cuts, len(line)]
    return [line[a:b] for a, b in itertools.pairwise(bounds)]


def _ass_zh(text: str, wrap: Wrap) -> str:
    return _ASS_SOFT_BREAK.join(_ass_escape(part) for part in wrap_line(text, wrap))


def _ass_escape(text: str) -> str:
    text = _ASS_BACKSLASH_HAZARD.sub(lambda m: m.group() + _ASS_JOINER, text)
    return text.replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def render_ass(cues: Iterable[Cue], wrap: Wrap = Wrap.CJK) -> str:
    events: list[str] = []
    for cue in _check_unique_ids(list(cues)):
        zh = (
            "\\N".join(_ass_zh(line, wrap) for line in cue.zh.split("\n")) + "\\N" if cue.zh else ""
        )
        text = f"{zh}{_ASS_EN_MARK}{_ass_escape(cue.en)}"
        start, end = _ass_time(cue.start_ms), _ass_time(cue.end_ms)
        events.append(f"Dialogue: 0,{start},{end},Zh,{cue.id},0,0,0,,{text}\n")
    return _ASS_HEADER + "".join(events)


def _ass_unescape(text: str) -> str:
    def decode(match: re.Match[str]) -> str:
        token = match.group()
        return {
            "\\N": "\n",
            "\\n": "\n",
            "\\{": "{",
            "\\}": "}",
            "\\" + _ASS_JOINER: "\\",
        }.get(token, "")

    text = text.replace(_ASS_SOFT_BREAK, "")
    lines = (line.strip() for line in _ASS_TOKEN.sub(decode, text).split("\n"))
    return "\n".join(line for line in lines if line)


def _ass_ms(lineno: int, value: str) -> int:
    match = _ASS_TIME.fullmatch(value.strip())
    if match is None or int(match.group(2)) >= 60 or int(match.group(3)) >= 60:
        raise FormatError(f"line {lineno}: bad ASS time {value!r}")
    hours, minutes, seconds, centis = (int(g) for g in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + centis * 10


def parse_ass(text: str) -> list[Cue]:
    rows: list[_RawCue] = []
    section = ""
    columns: dict[str, int] | None = None
    for lineno, raw in enumerate(_lines(text), start=1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line
        elif section != "[Events]":
            continue
        elif line.startswith("Format:"):
            names = [name.strip() for name in line.removeprefix("Format:").split(",")]
            columns = {name: index for index, name in enumerate(names)}
        elif line.startswith("Dialogue:"):
            if columns is None:
                raise FormatError(f"line {lineno}: Dialogue before an [Events] Format line")
            missing = {"Start", "End", "Text"} - columns.keys()
            if missing:
                raise FormatError(
                    f"line {lineno}: the [Events] Format line has no {sorted(missing)} column"
                )
            fields = line.removeprefix("Dialogue:").lstrip().split(",", len(columns) - 1)
            if len(fields) != len(columns):
                raise FormatError(f"line {lineno}: expected {len(columns)} Dialogue fields")
            before, mark, after = fields[columns["Text"]].partition(_ASS_EN_MARK)
            if not mark:
                raise FormatError(f"line {lineno}: not a bilingual file: no {_ASS_EN_MARK} marker")
            name = fields[columns["Name"]].strip() if "Name" in columns else ""
            rows.append(
                _RawCue(
                    lineno,
                    name,
                    _ass_ms(lineno, fields[columns["Start"]]),
                    _ass_ms(lineno, fields[columns["End"]]),
                    _ass_unescape(after),
                    _ass_unescape(before.removesuffix("\\N")),
                )
            )
    return _build_cues(rows)


def _json_object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FormatError(f"{where} must be a JSON object")
    return {str(k): v for k, v in cast("dict[object, object]", value).items()}


def _json_list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise FormatError(f"{where} must be a JSON array")
    return list(cast("list[object]", value))


def _json_int(value: object, where: str) -> int:
    if type(value) is not int:
        raise FormatError(f"{where} must be an integer, got {value!r}")
    return value


def _json_str(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise FormatError(f"{where} must be a string, got {value!r}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FormatError(f"{where} contains a lone surrogate at index {exc.start}") from exc
    return value


def _json_keys(
    obj: Mapping[str, object], keys: set[str], where: str, optional: set[str] | None = None
) -> None:
    if not keys <= set(obj) <= keys | (optional or set()):
        raise FormatError(f"{where} must have exactly the keys {sorted(keys)}, got {sorted(obj)}")


def _load_json(text: str, where: str) -> dict[str, object]:
    try:
        return _json_object(json.loads(text.removeprefix("\ufeff")), where)
    except json.JSONDecodeError as exc:
        raise FormatError(f"{where}: invalid JSON ({exc})") from exc


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def render_subs(cues: Iterable[Cue]) -> str:
    return _dump_json(
        {
            "schema_version": SUBS_SCHEMA_VERSION,
            "cues": [
                {
                    "id": cue.id,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms,
                    "en": cue.en,
                    "zh": cue.zh,
                }
                for cue in _check_unique_ids(list(cues))
            ],
        }
    )


def parse_subs(text: str) -> list[Cue]:
    doc = _load_json(text, "subs file")
    version = doc.get("schema_version")
    if version is None:
        raise FormatError("subs file has no schema_version")
    if type(version) is not int or version != SUBS_SCHEMA_VERSION:
        raise FormatError(f"unsupported subs schema_version {version!r}")
    _json_keys(doc, {"schema_version", "cues"}, "subs file")
    cues: list[Cue] = []
    for index, item in enumerate(_json_list(doc["cues"], "cues")):
        where = f"cues[{index}]"
        obj = _json_object(item, where)
        _json_keys(obj, {"id", "start_ms", "end_ms", "en", "zh"}, where)
        try:
            cues.append(
                Cue(
                    _json_int(obj["id"], f"{where}.id"),
                    _json_int(obj["start_ms"], f"{where}.start_ms"),
                    _json_int(obj["end_ms"], f"{where}.end_ms"),
                    _json_str(obj["en"], f"{where}.en"),
                    _json_str(obj["zh"], f"{where}.zh"),
                )
            )
        except ValueError as exc:
            raise FormatError(f"{where}: {exc}") from exc
    return _check_unique_ids(cues)


def _render_steps(steps: Mapping[Step, StepState]) -> dict[str, object]:
    return {
        step.value: {
            "status": state.status.value,
            "updated_at_ms": state.updated_at_ms,
            "error": state.error,
            **({"key": state.key} if state.key is not None else {}),
        }
        for step, state in steps.items()
    }


def render_project(project: Project) -> str:
    """`active_lang` and `parked` are written only when the project has left the default
    language, so a project that never did reads the same as before they existed."""
    doc: dict[str, object] = {
        "schema_version": project.schema_version,
        "video_path": project.video_path,
        "steps": _render_steps(project.steps),
    }
    if project.active_lang != DEFAULT_CODE:
        doc["active_lang"] = project.active_lang
    if project.parked:
        doc["parked"] = {lang: _render_steps(states) for lang, states in project.parked.items()}
    return _dump_json(doc)


def _parse_steps(raw: object, where: str) -> dict[Step, StepState]:
    raw_steps = _json_object(raw, where)
    unknown = raw_steps.keys() - {step.value for step in Step}
    if unknown:
        raise FormatError(f"{where} has unknown step names {sorted(unknown)}")
    steps: dict[Step, StepState] = {}
    for name, item in raw_steps.items():
        here = f"{where}.{name}"
        obj = _json_object(item, here)
        _json_keys(obj, {"status", "updated_at_ms", "error"}, here, optional={"key"})
        updated, error, key = obj["updated_at_ms"], obj["error"], obj.get("key")
        try:
            steps[Step(name)] = StepState(
                StepStatus(_json_str(obj["status"], f"{here}.status")),
                None if updated is None else _json_int(updated, f"{here}.updated_at_ms"),
                None if error is None else _json_str(error, f"{here}.error"),
                None if key is None else _json_str(key, f"{here}.key"),
            )
        except ValueError as exc:
            raise FormatError(f"{here}: {exc}") from exc
    return steps


def _language(code: object, where: str) -> str:
    text = _json_str(code, where)
    try:
        return get_language(text).code
    except UnknownLanguage as exc:
        raise FormatError(f"{where}: {exc}") from exc


def parse_project(text: str) -> Project:
    doc = Project.migrate(_load_json(text, "project.json"))
    _json_keys(
        doc,
        {"schema_version", "video_path", "steps"},
        "project.json",
        optional={"active_lang", "parked"},
    )
    steps = _parse_steps(doc["steps"], "steps")
    active = _language(doc.get("active_lang", DEFAULT_CODE), "active_lang")
    parked = {
        _language(lang, "parked"): _parse_steps(states, f"parked.{lang}")
        for lang, states in _json_object(doc.get("parked", {}), "parked").items()
    }
    try:
        return Project(
            _json_str(doc["video_path"], "video_path"),
            steps,
            _json_int(doc["schema_version"], "schema_version"),
            active,
            parked,
        )
    except ValueError as exc:
        raise FormatError(f"project.json: {exc}") from exc
