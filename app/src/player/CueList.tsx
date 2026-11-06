import { Pencil } from "lucide-react";
import { type KeyboardEvent, memo, useEffect, useRef } from "react";
import { CueEditor, type EditorHooks } from "../editor/CueEditor";
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
  readonly edited: boolean;
  readonly editor: EditorHooks | null;
  readonly onSeek: (cue: Cue) => void;
  readonly onEdit: (id: number) => void;
}

/** Memoized so a cue change re-renders the two rows whose `active` flipped, not the whole list. */
const Row = memo(function Row({ cue, n, active, mode, edited, editor, onSeek, onEdit }: RowProps) {
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "F2") {
      e.preventDefault();
      onEdit(cue.id);
    }
  };
  const button = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    if (wasEditing.current && !editor && document.activeElement === document.body) button.current?.focus();
    wasEditing.current = editor !== null;
  }, [editor]);
  return (
    <li
      data-testid={`cue-${n}`}
      data-active={active}
      data-edited={edited}
      data-editing={editor !== null}
      data-start={cue.startMs}
    >
      {editor ? (
        <CueEditor cue={cue} hooks={editor} />
      ) : (
        <button
          ref={button}
          type="button"
          title="按兩下或 F2 編輯"
          onClick={() => onSeek(cue)}
          onDoubleClick={() => onEdit(cue.id)}
          onKeyDown={onKey}
        >
          <span className="time">
            {clock(cue.startMs)}
            {edited && <Pencil className="edited-mark" aria-label="已手動修改" data-testid="edited-mark" />}
          </span>
          <span className="text">
            {mode !== "zh" && <span className="en">{cue.en}</span>}
            {mode !== "en" && <span className="zh">{cue.zh}</span>}
          </span>
        </button>
      )}
    </li>
  );
});

interface Props {
  readonly cues: readonly Cue[];
  readonly active: number;
  readonly mode: SubtitleMode;
  readonly edited: ReadonlySet<number>;
  readonly editingId: number | null;
  /** Hooks for the editor of the cue being edited. */
  readonly editor: (cue: Cue) => EditorHooks;
  readonly onSeek: (cue: Cue) => void;
  readonly onEdit: (id: number) => void;
}

export function CueList({ cues, active, mode, edited, editingId, editor, onSeek, onEdit }: Props) {
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
        <Row
          key={cue.id}
          cue={cue}
          n={i + 1}
          active={i === active}
          mode={mode}
          edited={edited.has(cue.id)}
          editor={cue.id === editingId ? editor(cue) : null}
          onSeek={onSeek}
          onEdit={onEdit}
        />
      ))}
    </ol>
  );
}
