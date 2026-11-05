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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
from backend.core.summarize import Lang

SubFormat = Literal["srt", "vtt", "ass", "json"]
_ID = re.compile(r"[0-9a-f]{16}")
MEDIA_TYPES: dict[SubFormat, str] = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "ass": "text/x-ssa",
    "json": "application/json",
}


class UnknownProject(LookupError):
    pass


class NotReady(Exception):
    """The file asked for does not exist yet because a step has not finished."""


class BadCues(ValueError):
    """Corrected cues that do not fit the project's cues."""


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
        files = {f.value: folder / f.value for f in File if (folder / f.value).is_file()}
        return ProjectInfo(pid, folder, project, files)

    def _done(self, info: ProjectInfo, step: Step) -> bool:
        return info.project.steps[step].status is StepStatus.DONE

    def cues(self, pid: str) -> list[Cue]:
        """The translated cues once translation has finished, else the English ones."""
        info = self.info(pid)
        if self._done(info, Step.TRANSLATE):
            return parse_subs(read_text_file(info.folder / File.SUBS_ZH))
        if self._done(info, Step.SEGMENT):
            return parse_subs(read_text_file(info.folder / File.SUBS_EN))
        raise NotReady("no subtitles yet: the segment step has not finished")

    def subtitles(self, pid: str, lang: RenderLang, fmt: SubFormat) -> str:
        info = self.info(pid)
        if lang != "en" and not self._done(info, Step.TRANSLATE):
            raise NotReady("no Chinese subtitles yet: the translate step has not finished")
        if fmt == "ass" and lang != "bilingual":
            raise ValueError("ass is only available as bilingual")
        cues = self.cues(pid)
        match fmt:
            case "srt":
                return render_srt(cues, lang)
            case "vtt":
                return render_vtt(cues, lang)
            case "ass":
                return render_ass(cues)
            case "json":
                return render_subs(cues)

    def summary(self, pid: str, lang: Lang) -> bytes:
        info = self.info(pid)
        name = File.SUMMARY if lang == "zh-TW" else File.SUMMARY_EN
        if not self._done(info, Step.SUMMARIZE) or name.value not in info.files:
            raise NotReady(f"no {lang} summary yet: the summarize step has not finished")
        return info.files[name.value].read_bytes()

    def save_cues(self, pid: str, cues: Sequence[Cue]) -> None:
        """Replace the translated cues with corrected ones that keep the same ids. The caller
        makes sure no job is running on the project."""
        info = self.info(pid)
        if not self._done(info, Step.TRANSLATE):
            raise NotReady("nothing to correct yet: the translate step has not finished")
        current = [c.id for c in self.cues(pid)]
        if sorted(c.id for c in cues) != sorted(current):
            raise BadCues("the cues must have exactly the ids the project has")
        ordered = sorted(cues, key=lambda c: (c.start_ms, c.id))
        save_edited_cues(info.folder, ordered)
