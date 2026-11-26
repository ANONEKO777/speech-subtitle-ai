import { Pencil, TriangleAlert } from "lucide-react";
import { type KeyboardEvent, memo, useEffect, useRef } from "react";
import { useT } from "../i18n/I18nProvider";
import { CueEditor, type EditorHooks } from "../editor/CueEditor";
import { type Cue, type SubtitleMode } from "./cues";
import { type FailedKind, failureTitle } from "./failures";
import { LangMark } from "./LangMark";

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
  readonly marks: boolean;
  /** The translation of this cue failed, and what the cue shows instead. */
  readonly failed: FailedKind | undefined;
  /** The name of the language the cues are translated into. */
  readonly target: string;
  readonly editor: EditorHooks | null;
  readonly onSeek: (cue: Cue) => void;
  readonly onEdit: (id: number) => void;
}

/** Memoized so a cue change re-renders the two rows whose `active` flipped, not the whole list. */
const Row = memo(function Row({ cue, n, active, mode, edited, marks, failed, target, editor, onSeek, onEdit }: RowProps) {
  const { t } = useT();
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
      data-failed={failed}
      data-editing={editor !== null}
      data-start={cue.startMs}
    >
      {editor ? (
        <CueEditor cue={cue} hooks={editor} marks={marks} />
      ) : (
        <button
          ref={button}
          type="button"
          title={t("player.cue.edit")}
          onClick={() => onSeek(cue)}
          onDoubleClick={() => onEdit(cue.id)}
          onKeyDown={onKey}
        >
          <span className="time">
            {clock(cue.startMs)}
            {edited && <Pencil className="edited-mark" aria-label={t("player.cue.edited")} data-testid="edited-mark" />}
            {failed && (
              <span className="failed-mark" role="img" aria-label={t("player.cue.failed")} title={failureTitle(failed, target, t)} data-testid="failed-mark" data-kind={failed}>
                <TriangleAlert className="icon" aria-hidden />
              </span>
            )}
          </span>
          <span className="text">
            {mode !== "zh" && (
              <span className="src" lang={cue.lang} data-cue-lang={cue.lang}>
                {marks && <LangMark lang={cue.lang} />}
                {cue.src}
              </span>
            )}
            {mode !== "en" && (failed === "empty" ? <span className="zh missing">{t("player.cue.none")}</span> : <span className="zh">{cue.zh}</span>)}
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
  /** Whether each cue shows its language, as in a mixed talk. */
  readonly marks: boolean;
  readonly edited: ReadonlySet<number>;
  /** The cues the translator could not do, by id. */
  readonly failed: ReadonlyMap<number, FailedKind>;
  /** Show only the cues in `failed`. */
  readonly onlyFailed: boolean;
  readonly target: string;
  readonly editingId: number | null;
  /** Hooks for the editor of the cue being edited. */
  readonly editor: (cue: Cue) => EditorHooks;
  readonly onSeek: (cue: Cue) => void;
  readonly onEdit: (id: number) => void;
}

export function CueList({ cues, active, mode, marks, edited, failed, onlyFailed, target, editingId, editor, onSeek, onEdit }: Props) {
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const box = list.current;
    const item = box?.querySelector('[data-active="true"]');
    if (!box || !(item instanceof HTMLElement)) return;
    const edge = box.getBoundingClientRect();
    const row = item.getBoundingClientRect();
    if (row.top < edge.top) box.scrollTop += row.top - edge.top;
    else if (row.bottom > edge.bottom) box.scrollTop += row.bottom - edge.bottom;
  }, [active]);

  return (
    <ol className="cues" ref={list} data-testid="cue-list">
      {cues.map((cue, i) =>
        onlyFailed && !failed.has(cue.id) ? null : (
        <Row
          key={cue.id}
          cue={cue}
          n={i + 1}
          active={i === active}
          mode={mode}
          marks={marks}
          edited={edited.has(cue.id)}
          failed={failed.get(cue.id)}
          target={target}
          editor={cue.id === editingId ? editor(cue) : null}
          onSeek={onSeek}
          onEdit={onEdit}
        />
        ),
      )}
    </ol>
  );
}
