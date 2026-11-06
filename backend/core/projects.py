"""Projects on disk, as the API sees them.

A project is a folder under `root` named by the id of its video, so creating the same project
twice finds the same folder and a restarted service finds every project without an index. The
files inside belong to the pipeline. This module reads them, and saves corrected cues through
`pipeline.save_edited_cues`.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Sequence
from dataclasses import astuple, dataclass
from pathlib import Path
from typing import Literal

from backend.core import cue_edits
from backend.core.cue_edits import CueProblem
from backend.core.languages import ENGLISH, LANGUAGES, get
from backend.core.model import Cue, FormatError, Project, Step, StepStatus
from backend.core.pipeline import PROJECT_JSON, File, save_edited_cues
from backend.core.subtitle_io import (
    RenderLang,
    parse_project,
    parse_subs,
    read_text_file,
    render_ass,
    render_project,
    render_srt,
    render_subs,
    render_vtt,
    write_text_file,
)
from backend.core.summarize import ENGLISH_SUMMARY_FILE, Lang

SubFormat = Literal["srt", "vtt", "ass", "json"]
_ID = re.compile(r"[0-9a-f]{16}")
MEDIA_TYPES: dict[SubFormat, str] = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "ass": "text/x-ssa",
    "json": "application/json",
}


_KNOWN_FILES = tuple(
    dict.fromkeys(
        [
            *(f.value for f in File),
            *(name for lang in LANGUAGES.values() for name in astuple(lang.files)),
        ]
    )
)


class UnknownProject(LookupError):
    pass


class NotReady(Exception):
    """The file asked for does not exist yet because a step has not finished."""


class BadCues(ValueError):
    """Corrected cues that do not fit the project's cues. `problems` names the cues at fault."""

    def __init__(self, message: str, problems: Sequence[CueProblem] = ()) -> None:
        super().__init__(message)
        self.problems = tuple(problems)


def project_id(video: Path) -> str:
    key = os.path.normcase(os.path.abspath(video))
    return hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    id: str
    folder: Path
    project: Project
    files: dict[str, Path]


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, video: Path) -> tuple[ProjectInfo, bool]:
        """Make the project for `video`, or find it. Returns the project and whether it is new."""
        pid = project_id(video)
        folder = self.root / pid
        path = folder / PROJECT_JSON
        created = not path.is_file()
        if created:
            folder.mkdir(parents=True, exist_ok=True)
            write_text_file(path, render_project(Project(str(video.absolute()))))
        return self.info(pid), created

    def folder(self, pid: str) -> Path:
        folder = self.root / pid
        if not _ID.fullmatch(pid) or not (folder / PROJECT_JSON).is_file():
            raise UnknownProject(pid)
        return folder

    def info(self, pid: str) -> ProjectInfo:
        folder = self.folder(pid)
        try:
            project = parse_project(read_text_file(folder / PROJECT_JSON))
        except FormatError as exc:
            raise UnknownProject(f"{pid}: {exc}") from exc
        files = {name: folder / name for name in _KNOWN_FILES if (folder / name).is_file()}
        return ProjectInfo(pid, folder, project, files)

    def _done(self, info: ProjectInfo, step: Step, lang: str) -> bool:
        return info.project.state(step, lang).status is StepStatus.DONE

    def active_lang(self, pid: str) -> str:
        """The language the project was last worked on."""
        return self.info(pid).project.active_lang

    def cues(self, pid: str, target: str | None = None) -> list[Cue]:
        """The cues translated into `target` (the active language by default) once translation
        has finished, else the English ones."""
        info = self.info(pid)
        lang = get(target or info.project.active_lang)
        if self._done(info, Step.TRANSLATE, lang.code):
            return parse_subs(read_text_file(info.folder / lang.files.subs))
        if self._done(info, Step.SEGMENT, lang.code):
            return parse_subs(read_text_file(info.folder / File.SUBS_EN))
        raise NotReady("no subtitles yet: the segment step has not finished")

    def subtitles(
        self, pid: str, lang: RenderLang, fmt: SubFormat, target: str | None = None
    ) -> str:
        """`lang` picks which texts to show. `zh` is the text in the target language, whatever
        language `target` is."""
        info = self.info(pid)
        code = get(target or info.project.active_lang).code
        if lang != "en" and not self._done(info, Step.TRANSLATE, code):
            raise NotReady(f"no {code} subtitles yet: the translate step has not finished")
        if fmt == "ass" and lang != "bilingual":
            raise ValueError("ass is only available as bilingual")
        cues = self.cues(pid, code)
        match fmt:
            case "srt":
                return render_srt(cues, lang)
            case "vtt":
                return render_vtt(cues, lang)
            case "ass":
                return render_ass(cues, get(code).wrap)
            case "json":
                return render_subs(cues)

    def summary(self, pid: str, lang: Lang | None = None) -> bytes:
        info = self.info(pid)
        code = lang or info.project.active_lang
        name = ENGLISH_SUMMARY_FILE if code == ENGLISH else get(code).files.summary
        if code == ENGLISH:
            done = any(
                states[Step.SUMMARIZE].status is StepStatus.DONE
                for states in info.project.languages().values()
            )
        else:
            done = self._done(info, Step.SUMMARIZE, code)
        if not done or name not in info.files:
            raise NotReady(f"no {code} summary yet: the summarize step has not finished")
        return info.files[name].read_bytes()

    def save_cues(self, pid: str, cues: Sequence[Cue], target: str | None = None) -> None:
        """Replace the translated cues with corrected ones that keep the same ids and English
        lines, and remember which ones changed. The caller makes sure no job is running on the
        project."""
        info = self.info(pid)
        lang = get(target or info.project.active_lang)
        if not self._done(info, Step.TRANSLATE, lang.code):
            raise NotReady("nothing to correct yet: the translate step has not finished")
        current = [c.id for c in self.cues(pid, lang.code)]
        if sorted(c.id for c in cues) != sorted(current):
            raise BadCues("the cues must have exactly the ids the project has")
        problems = cue_edits.check(self.cues(pid, lang.code), cues)
        if problems:
            raise BadCues(f"{len(problems)} cues cannot be saved", problems)
        cue_edits.record(info.folder, lang, self.cues(pid, lang.code), cues)
        save_edited_cues(info.folder, sorted(cues, key=lambda c: c.id), lang)

    def edited_ids(self, pid: str, target: str | None = None) -> list[int]:
        """The ids of the cues a person corrected in `target` that a rerun kept. An edit whose
        English line changed stays in the edits file and is not listed."""
        info = self.info(pid)
        lang = get(target or info.project.active_lang)
        return [c.id for c in cue_edits.applied(info.folder, lang)]
