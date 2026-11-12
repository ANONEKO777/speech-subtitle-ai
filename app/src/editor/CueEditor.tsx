import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import type { Cue } from "../player/cues";
import { BACKEND_PROBLEM, type Draft, formatClock, normalizeText, parseClock } from "./validate";

export interface EditorHooks {
  /** The reason the draft cannot be saved, or null. */
  readonly validate: (draft: Draft) => string | null;
  /** The backend's reason for refusing the last save, shown until the next attempt. */
  readonly refusal: string | null;
  readonly onCommit: (draft: Draft) => Promise<boolean>;
  readonly onCancel: () => void;
}

const BAD_TIME = "時間格式為 分:秒.毫秒，例如 1:05.250";
const SOURCE_LOCKED = BACKEND_PROBLEM["english_changed"] ?? "";

/** Inline editor for one cue: the target language text and the two times. The source line is shown for reference and cannot be changed. */
export function CueEditor({ cue, hooks }: { readonly cue: Cue; readonly hooks: EditorHooks }) {
  const [zh, setZh] = useState(cue.zh);
  const [start, setStart] = useState(formatClock(cue.startMs));
  const [end, setEnd] = useState(formatClock(cue.endMs));
  const root = useRef<HTMLDivElement>(null);
  const over = useRef(false);
  const [typedOnSource, setTypedOnSource] = useState(false);
  const errorLine = useRef<HTMLParagraphElement>(null);

  const startMs = parseClock(start);
  const endMs = parseClock(end);
  const draft = startMs === null || endMs === null ? null : { zh: normalizeText(zh), startMs, endMs };
  const problem = draft === null ? BAD_TIME : (hooks.validate(draft) ?? hooks.refusal ?? (typedOnSource ? SOURCE_LOCKED : null));

  useEffect(() => {
    const line = errorLine.current;
    const list = line?.closest("ol");
    if (!line || !list) return;
    const hidden = line.getBoundingClientRect().bottom - list.getBoundingClientRect().bottom;
    if (hidden > 0) list.scrollTop += hidden;
  }, [problem]);

  const commit = async () => {
    if (over.current || draft === null) return;
    over.current = true;
    over.current = await hooks.onCommit(draft);
  };

  const cancel = () => {
    over.current = true;
    hooks.onCancel();
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      cancel();
    } else if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void commit();
    }
  };

  return (
    <div
      className="editor"
      ref={root}
      data-testid="cue-editor"
      data-invalid={problem !== null}
      onKeyDown={onKey}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node | null)) void commit();
      }}
    >
      <div className="editor-times">
        <label>
          <span>開始</span>
          <input
            data-testid="edit-start"
            value={start}
            inputMode="decimal"
            spellCheck={false}
            aria-invalid={startMs === null}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          <span>結束</span>
          <input
            data-testid="edit-end"
            value={end}
            inputMode="decimal"
            spellCheck={false}
            aria-invalid={endMs === null}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
      </div>
      <textarea
        data-testid="edit-text"
        aria-label="字幕文字"
        value={zh}
        rows={Math.max(2, zh.split("\n").length)}
        autoFocus
        onFocus={(e) => e.currentTarget.setSelectionRange(zh.length, zh.length)}
        onChange={(e) => setZh(e.target.value)}
      />
      <p
        className="editor-src"
        data-testid="edit-source"
        lang={cue.lang}
        tabIndex={0}
        title="原文是翻譯與摘要的來源，不能在這裡修改"
        onKeyDown={(e) => {
          if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.stopPropagation();
            setTypedOnSource(true);
          }
        }}
        onPaste={() => setTypedOnSource(true)}
      >
        {cue.src}
      </p>
      {problem && (
        <p className="editor-error" role="alert" data-testid="edit-error" ref={errorLine}>
          {problem}
        </p>
      )}
      <p className="editor-hint">Enter 儲存 · Shift+Enter 換行 · Esc 取消</p>
    </div>
  );
}
