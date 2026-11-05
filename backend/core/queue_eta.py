"""How long the queue will take, from how long recent steps took per second of audio.

A step's rate is the seconds it spent per second of audio over its last runs, and only runs that
did work count (a cached step takes no time and says nothing). An item's cost is the sum of its
steps' rates times its audio length. Translation speed depends on the language and the text, so
the figure is an estimate and says nothing before a first item has finished.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from backend.core.jobs import BEFORE, STEP_WEIGHTS
from backend.core.model import Step
from backend.core.queue_store import ItemState, QueueItem, StepTiming


@dataclass(frozen=True, slots=True)
class Live:
    """Where the running item is. `fraction` is the share of `step` done."""

    job_id: str
    step: Step | None
    overall: float
    fraction: float


def live_from_overall(job_id: str, step: Step | None, overall: float) -> Live:
    if step is None:
        return Live(job_id, None, overall, 0.0)
    fraction = (overall - BEFORE[step]) / STEP_WEIGHTS[step]
    return Live(job_id, step, overall, min(max(fraction, 0.0), 1.0))


def step_rates(timings: Iterable[StepTiming]) -> Mapping[Step, float]:
    seconds: dict[Step, float] = {}
    audio: dict[Step, float] = {}
    for t in timings:
        step = Step(t.step)
        seconds[step] = seconds.get(step, 0.0) + t.seconds
        audio[step] = audio.get(step, 0.0) + t.audio_s
    return {step: seconds[step] / audio[step] for step in seconds if audio[step] > 0}


def remaining_s(rates: Mapping[Step, float], audio_s: float, live: Live | None) -> float:
    """Seconds still to spend on an item: all steps, or the rest of the steps after `live`."""
    total = 0.0
    for index, step in enumerate(Step):
        rate = rates.get(step, 0.0) * audio_s
        if live is None or live.step is None:
            total += rate
        elif index == list(Step).index(live.step):
            total += rate * (1.0 - live.fraction)
        elif index > list(Step).index(live.step):
            total += rate
    return total


def etas(
    items: Sequence[QueueItem], live: Live | None, rates: Mapping[Step, float]
) -> dict[str, float | None]:
    """Seconds until each running or queued item finishes, in queue order. An item of unknown
    length counts as no time, because it is most likely a bad file that fails at once. Everything
    is None until a first item has produced rates. Paused and finished items have no ETA."""
    out: dict[str, float | None] = {}
    clock = 0.0
    ordered = sorted(
        (i for i in items if i.state in (ItemState.RUNNING, ItemState.QUEUED)),
        key=lambda i: (i.state is not ItemState.RUNNING, i.position),
    )
    for item in ordered:
        running = item.state is ItemState.RUNNING
        if rates and item.audio_s is not None:
            clock += remaining_s(rates, item.audio_s, live if running else None)
        out[item.id] = clock if rates else None
    return out
