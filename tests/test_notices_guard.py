"""A sentence the window shows must have a code, or it stays English in every other language.

This reads the files whose sentences the W4b round gave codes to, and fails on an English sentence
written where one leaves for the window: in an error that is raised, in a download failure, in what
a function returns, or in a variable named like a message. `backend/core/notices.py` is where such
a sentence goes (its module docstring has the steps). A sentence the window never shows is listed
in `NOT_SHOWN` with the reason.

It looks at those places only, because two of the files are mostly prompts for the model. It does
not see a sentence handed to a call that is not in `SHOWN_CALLS` (the batch's list of skipped
files, the retry note of a download), one in a `ValueError`, one of a single word, or one in a
file outside `GUARDED`.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"

GUARDED = (
    "api/deps.py",
    "api/downloads.py",
    "api/inventory.py",
    "api/jobs.py",
    "api/models.py",
    "api/player.py",
    "api/profile.py",
    "api/projects.py",
    "api/queue.py",
    "api/runtimes.py",
    "api/settings.py",
    "core/audio.py",
    "core/cue_edits.py",
    "core/pipeline.py",
    "core/projects.py",
    "core/queue_runner.py",
    "core/queue_store.py",
    "core/render.py",
    "core/summarize.py",
    "core/translate.py",
    "engines/base.py",
    "engines/chunks.py",
    "engines/crispasr.py",
    "engines/mixed.py",
    "engines/table.py",
    "engines/whispercpp.py",
    "llm/ask.py",
    "llm/client.py",
    "llm/local_server.py",
    "main.py",
    "manager/download.py",
    "manager/inventory.py",
    "manager/llm_check.py",
    "manager/maintain.py",
    "manager/profiles.py",
    "manager/resolve.py",
    "manager/secrets.py",
    "manager/selftest.py",
    "manager/settings.py",
    "manager/storage.py",
    "manager/storage_move.py",
    "manager/switch.py",
    "manager/updates.py",
)

# Errors whose words stay inside the backend: a broken call, a stop the window words itself, and
# what the check of a model's answer says back to the model.
INTERNAL_ERRORS = frozenset(
    {
        "AssertionError",
        "Cancelled",
        "EngineCancelled",
        "ExtractCancelled",
        "NotImplementedError",
        "ReplyError",
        "TypeError",
        "ValueError",
    }
)
# Calls that build what is shown, wherever they are written.
# `finish` is how the batch stores why an item stopped (`store.finish(id, state, error)`).
SHOWN_CALLS = frozenset(
    {"Failure", "HTTPException", "UpdateItem", "UpdateReport", "_Transient", "finish"}
)
MESSAGE_NAMES = frozenset(
    {"detail", "error", "message", "msg", "note", "reason", "summary", "warning", "warnings", "why"}
)

# (file, how the sentence starts, why the window never shows it). `{}` stands for a value.
NOT_SHOWN: tuple[tuple[str, str, str], ...] = (
    ("api/jobs.py", "job {} is already running", "the window words every 409 of this route"),
    ("api/jobs.py", "unknown job", "an id the window got from the backend"),
    ("api/jobs.py", "id: {}", "the framing of the event stream"),
    ("core/audio.py", "{} did not finish in", "a piece cut to name a language: a silent guess"),
    ("core/summarize.py", "Your last reply was rejected", "said to the model"),
    ("engines/chunks.py", "{} gives no word timestamps", "both engines give them"),
    ("engines/whispercpp.py", "{}: cannot start", "naming a language: a silent guess"),
    ("engines/whispercpp.py", "{} did not name", "naming a language: a silent guess"),
    ("engines/whispercpp.py", "{} exited with code", "naming a language: a silent guess"),
    ("engines/whispercpp.py", "{} named {} languages", "naming a language: a silent guess"),
    ("llm/local_server.py", "cancelled while", "a stop, which the window words itself"),
    ("manager/resolve.py", "--llm-model is required", "only a hand-written request raises it"),
    ("manager/resolve.py", "--llm {} is not a URL", "only a hand-written request raises it"),
    ("api/downloads.py", "unknown download", "an id the window got from the backend"),
    ("api/queue.py", "unknown queue item", "an id the window got from the backend"),
    ("api/queue.py", "{} speech can be translated", "the batch dialog offers only these targets"),
    ("api/projects.py", "{}; charset=utf-8", "a media type"),
    ("api/projects.py", "text/markdown; charset=utf-8", "a media type"),
    ("api/projects.py", "some cues are not valid", "the editor words each cue's problem code"),
    ("core/projects.py", "{} cues cannot be saved", "the editor words each cue's problem code"),
    ("core/projects.py", "no {} summary yet", "the export menu asks first and words it itself"),
    (
        "core/queue_store.py",
        "on_done {} needs allow_power",
        "only a hand-written request raises it",
    ),
    ("core/queue_store.py", "SELECT {} FROM items", "SQL"),
    ("core/queue_store.py", "UPDATE items SET state", "SQL"),
    ("manager/storage.py", "Application Support", "a folder name"),
    (
        "manager/storage.py",
        "storage config must be",
        "a hand-edited storage.json: storage.cannotRead quotes it",
    ),
    (
        "manager/storage.py",
        "mirrors must map",
        "a hand-edited storage.json: storage.cannotRead quotes it",
    ),
    (
        "manager/storage.py",
        "bad mirror",
        "a hand-edited storage.json: storage.cannotRead quotes it",
    ),
    (
        "manager/settings.py",
        "{} must be an object",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
    (
        "manager/settings.py",
        "{}: unexpected keys",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
    (
        "manager/settings.py",
        "{} must be a string",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
    (
        "manager/settings.py",
        "unsupported schema_version",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
    (
        "manager/settings.py",
        "cloud_consent must be true or false",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
    (
        "manager/settings.py",
        "registry_url must be a string or null",
        "a hand-edited settings.json: settings.fileNotUsed quotes it",
    ),
)

_WORD = re.compile(r"[A-Za-z]{2,}")


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(part.value) if isinstance(part, ast.Constant) else "{}" for part in node.values
        )
    return None


def _is_sentence(text: str) -> bool:
    return len(_WORD.findall(text.replace("{}", " "))) >= 2 and " " in text.strip()


def _literals(node: ast.AST) -> Iterator[tuple[int, str]]:
    """The sentences written inside `node`. An f-string is one sentence, not its parts."""
    if isinstance(node, ast.Call) and _name(node.func) == "cast":
        for value in node.args[1:]:
            yield from _literals(value)
        return
    text = _literal(node)
    if text is not None:
        if _is_sentence(text):
            yield getattr(node, "lineno", 0), text
        return
    for child in ast.iter_child_nodes(node):
        yield from _literals(child)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def _sinks(tree: ast.Module) -> Iterator[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if _name(node.exc.func) not in INTERNAL_ERRORS:
                yield node.exc
        elif isinstance(node, ast.Call) and _name(node.func) in SHOWN_CALLS:
            yield node
        elif isinstance(node, ast.Return) and node.value is not None:
            yield node.value
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_name(target) in MESSAGE_NAMES for target in targets):
                yield node.value


def sentences_without_a_code(root: Path) -> list[tuple[str, int, str]]:
    found: set[tuple[str, int, str]] = set()
    for file in GUARDED:
        tree = ast.parse((root / file).read_text(encoding="utf-8"))
        for sink in _sinks(tree):
            found.update((file, line, text) for line, text in _literals(sink))
    return sorted(found)


def _excused(file: str, text: str) -> list[int]:
    return [
        index
        for index, (where, start, _why) in enumerate(NOT_SHOWN)
        if where == file and text.startswith(start)
    ]


def test_every_sentence_that_leaves_for_the_window_has_a_code() -> None:
    new = [
        f"{file}:{line}: {text[:70]!r}"
        for file, line, text in sentences_without_a_code(BACKEND)
        if not _excused(file, text)
    ]

    assert not new, (
        "give each a Template in backend/core/notices.py and raise it with `noticed`, or list it "
        "in NOT_SHOWN with why the window never shows it: " + "; ".join(new)
    )


def test_no_excuse_outlives_its_sentence() -> None:
    used = {
        index
        for file, _line, text in sentences_without_a_code(BACKEND)
        for index in _excused(file, text)
    }
    stale = [NOT_SHOWN[i][:2] for i in range(len(NOT_SHOWN)) if i not in used]

    assert not stale, f"remove these from NOT_SHOWN: {stale}"
