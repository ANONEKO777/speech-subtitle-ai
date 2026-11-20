import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EXPERIMENTAL, type Target } from "../api/targets";
import { shortName } from "../export/exports";

interface Props {
  readonly targets: readonly Target[];
  /** The codes picked, in the order the backend lists the targets. */
  readonly value: readonly string[];
  readonly onChange: (codes: readonly string[]) => void;
  readonly label: string;
  readonly testid: string;
}

/** What the closed control says: the first language and how many more are picked. */
export function choiceSummary(targets: readonly Target[], value: readonly string[]): string {
  const names = targets.filter((t) => value.includes(t.code)).map((t) => shortName(t.nativeName));
  return names.length > 1 ? `${names[0] ?? ""} +${names.length - 1}` : (names[0] ?? "");
}

/** Picks one or more languages for a video. The last one picked cannot be taken away, so a video always has a target. */
export function TargetChoice({ targets, value, onChange, label, testid }: Props) {
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

  const toggle = (code: string) => {
    const next = value.includes(code) ? value.filter((c) => c !== code) : [...value, code];
    const ordered = targets.map((t) => t.code).filter((c) => next.includes(c));
    if (ordered.length > 0) onChange(ordered);
  };
  const several = targets.length > 1;
  return (
    <div
      className="target-choice"
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
        className="lang-select target-choice-button"
        data-testid={testid}
        data-codes={value.join(",")}
        aria-label={label}
        aria-haspopup="true"
        aria-expanded={open}
        disabled={!several}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{choiceSummary(targets, value)}</span>
        {several && <ChevronDown className="icon chevron" aria-hidden />}
      </button>
      {open && (
        <div className="target-choice-list" role="group" aria-label={label} data-testid={`${testid}-list`}>
          {targets.map((t) => (
            <label key={t.code}>
              <input
                type="checkbox"
                data-testid={`${testid}-${t.code}`}
                checked={value.includes(t.code)}
                disabled={value.length === 1 && value.includes(t.code)}
                onChange={() => toggle(t.code)}
              />
              <span>{shortName(t.nativeName)}</span>
              {t.experimental && <span className="chip-exp">{EXPERIMENTAL}</span>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
