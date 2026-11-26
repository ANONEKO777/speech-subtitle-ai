import { ChevronDown } from "lucide-react";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import type { Target } from "../api/targets";
import { useT } from "../i18n/I18nProvider";
import { type Locale, UNMANAGED_LOCALE } from "../i18n/locale";
import { langName } from "./lang";

interface Props {
  readonly targets: readonly Target[];
  /** The codes picked, in the order the backend lists the targets. */
  readonly value: readonly string[];
  readonly onChange: (codes: readonly string[]) => void;
  readonly label: string;
  readonly testid: string;
}

/** What the closed control says: the first language and how many more are picked. */
export function choiceSummary(targets: readonly Target[], value: readonly string[], locale: Locale = UNMANAGED_LOCALE): string {
  const names = targets.filter((x) => value.includes(x.code)).map((x) => langName(x.code, targets, locale));
  return names.length > 1 ? `${names[0] ?? ""} +${names.length - 1}` : (names[0] ?? "");
}

/** Picks one or more languages for a video. The last one picked cannot be taken away, so a video always has a target. */
export function TargetChoice({ targets, value, onChange, label, testid }: Props) {
  const { t, locale } = useT();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<CSSProperties>({});
  /** The list is placed against the window, so the scrolling list of rows around it cannot cut it off. It opens upward when there is no room below. */
  const openList = () => {
    const box = root.current?.getBoundingClientRect();
    if (box) {
      const below = window.innerHeight - box.bottom;
      const room = 28 * targets.length + 16;
      setPlace({ right: window.innerWidth - box.right, ...(below < room && box.top > room ? { bottom: window.innerHeight - box.top + 4 } : { top: box.bottom + 4 }) });
    }
    setOpen((v) => !v);
  };
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
    const ordered = targets.map((x) => x.code).filter((c) => next.includes(c));
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
        onClick={openList}
      >
        <span>{choiceSummary(targets, value, locale)}</span>
        {targets.some((x) => x.experimental && value.includes(x.code)) && (
          <span className="chip-exp" data-testid={`${testid}-experimental`}>
            {t("targets.experimental")}
          </span>
        )}
        {several && <ChevronDown className="icon chevron" aria-hidden />}
      </button>
      {open && (
        <div className="target-choice-list" style={place} role="group" aria-label={label} data-testid={`${testid}-list`}>
          {targets.map((x) => (
            <label key={x.code}>
              <input
                type="checkbox"
                data-testid={`${testid}-${x.code}`}
                checked={value.includes(x.code)}
                disabled={value.length === 1 && value.includes(x.code)}
                onChange={() => toggle(x.code)}
              />
              <span>{langName(x.code, targets, locale)}</span>
              {x.experimental && <span className="chip-exp">{t("targets.experimental")}</span>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
