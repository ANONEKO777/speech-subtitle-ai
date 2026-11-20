import { Languages } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EXPERIMENTAL, EXPERIMENTAL_HINT, type Target } from "../api/targets";
import { shortName } from "../export/exports";

interface Props {
  /** The languages the video can still be translated into. */
  readonly targets: readonly Target[];
  readonly disabled: boolean;
  readonly onAdd: (code: string) => void;
}

/** A menu of the subtitle languages this project lacks. Picking one translates the project again, without redoing the speech steps. */
export function AddTarget({ targets, disabled, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [open]);
  if (targets.length === 0) return null;
  return (
    <div
      className="menu"
      ref={root}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="ghost icon-button"
        data-testid="add-target"
        title="新增字幕語言：只重新翻譯，不重跑語音辨識"
        aria-label="新增字幕語言"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <Languages className="icon" aria-hidden />
      </button>
      {open && (
        <div className="menu-list add-target-list" role="menu" data-testid="add-target-list">
          <p className="menu-note">新增字幕語言，只會重新翻譯，不會重跑語音辨識。</p>
          {targets.map((t) => (
            <button key={t.code} type="button" role="menuitem" data-testid={`add-target-${t.code}`} onClick={() => {
              setOpen(false);
              onAdd(t.code);
            }}>
              {shortName(t.nativeName)}
              {t.experimental && <span className="chip-exp">{EXPERIMENTAL}</span>}
            </button>
          ))}
          {targets.some((t) => t.experimental) && (
            <p className="menu-note" data-testid="add-target-hint">
              {EXPERIMENTAL_HINT}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
