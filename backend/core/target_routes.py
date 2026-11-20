"""How one source language is translated into one target language, as a row of a table.

The source language's own fields describe the translation into its home target (for Japanese,
Traditional Chinese). Every other target a source supports is a `TargetRoute`: the rules text and
worked example the prompt gets, how long a translation may be, the checks and clean-up its text
must pass, the term table, the notes prompt of the summary, whether the language is experimental
and what happens to a cue that fails every attempt. Adding a target is adding a row and its
tests, not a branch in the code that translates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from backend.core.ja_terms import JaTerm
from backend.core.languages import Density


class OnFailure(StrEnum):
    """What a cue gets when every attempt at it failed."""

    KEEP_SOURCE = "keep_source"
    """The speaker's own words stay in the cue. This is what the home target has always done."""
    LEAVE_EMPTY = "leave_empty"
    """The cue has no translation and is counted as failed. Nothing in the source language is shown
    as if it were the translation."""
    ENGLISH_PIVOT = "english_pivot"
    """The cue is translated into English alone, with the English route of the same source, and the
    English is used when it passes that route's checks. Otherwise the cue is left empty. Either way
    the cue is counted as failed."""


@dataclass(frozen=True, slots=True)
class SummaryNotes:
    """What the notes prompt of the summary has for one target: the file that holds it and the
    text for its marks. The file's marks are `<<NOTES_RULE>>`, `<<POINT_LIMIT>>` and
    `<<TOPIC_LIMIT>>`."""

    file: str
    rule: str
    point_limit: str
    topic_limit: str

    @property
    def marks(self) -> dict[str, str]:
        return {
            "<<NOTES_RULE>>": self.rule,
            "<<POINT_LIMIT>>": self.point_limit,
            "<<TOPIC_LIMIT>>": self.topic_limit,
        }


@dataclass(frozen=True, slots=True)
class TargetRoute:
    """The fields of a `SourceLanguage` that change with the target. `rules` replaces the prompt's
    rules about the speech, `example` is the reply to the prompt's worked example and `leftover` is
    the rule about words left untranslated."""

    rules: str
    leftover: str
    example: str
    density: Density
    problem: Callable[[str], str | None]
    needs_script: Callable[[str], bool]
    """Whether the translation of this source text must hold characters of the target's script."""
    clean: Callable[[str], str]
    terms: tuple[JaTerm, ...]
    notes: SummaryNotes
    on_failure: OnFailure
    experimental: bool = False
