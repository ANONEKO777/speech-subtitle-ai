import { memo, useEffect, useRef } from "react";
import { type Cue, type SubtitleMode } from "./cues";

export function clock(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${m}:${ss}` : `${m}:${ss}`;
}

interface RowProps {
  readonly cue: Cue;
  readonly n: number;
  readonly active: boolean;
  readonly mode: SubtitleMode;
  readonly onSeek: (cue: Cue) => void;
}

/** Memoized so a cue change re-renders the two rows whose `active` flipped, not the whole list. */
const Row = memo(function Row({ cue, n, active, mode, onSeek }: RowProps) {
  return (
    <li data-testid={`cue-${n}`} data-active={active} data-start={cue.startMs}>
      <button type="button" onClick={() => onSeek(cue)}>
        <span className="time">{clock(cue.startMs)}</span>
        <span className="text">
          {mode !== "zh" && <span className="en">{cue.en}</span>}
          {mode !== "en" && <span className="zh">{cue.zh}</span>}
        </span>
      </button>
    </li>
  );
});

interface Props {
  readonly cues: readonly Cue[];
  readonly active: number;
  readonly mode: SubtitleMode;
  readonly onSeek: (cue: Cue) => void;
}

export function CueList({ cues, active, mode, onSeek }: Props) {
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const box = list.current;
    const item = box?.children[active];
    if (!box || !(item instanceof HTMLElement)) return;
    const edge = box.getBoundingClientRect();
    const row = item.getBoundingClientRect();
    if (row.top < edge.top) box.scrollTop += row.top - edge.top;
    else if (row.bottom > edge.bottom) box.scrollTop += row.bottom - edge.bottom;
  }, [active]);

  return (
    <ol className="cues" ref={list} data-testid="cue-list">
      {cues.map((cue, i) => (
        <Row key={cue.id} cue={cue} n={i + 1} active={i === active} mode={mode} onSeek={onSeek} />
      ))}
    </ol>
  );
}
