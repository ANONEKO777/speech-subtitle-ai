import { Languages } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Target } from "../api/targets";
import { useT } from "../i18n/I18nProvider";
import { languageLabel } from "./langName";

interface Props {
  /** The languages the video can still be translated into. */
  readonly targets: readonly Target[];
  /** Why adding is not possible now, shown as the button's tooltip. Null when it is. */
  readonly blocked: string | null;
  readonly onAdd: (code: string) => void;
}

/** A menu of the subtitle languages this project lacks. Picking one translates the project again, without redoing the speech steps. */
export function AddTarget({ targets, blocked, onAdd }: Props) {
  const { t, locale } = useT();
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
        title={blocked ?? t("player.addTargetTitle")}
        aria-label={t("player.addTarget")}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={blocked !== null}
        data-blocked={blocked !== null}
        onClick={() => setOpen((v) => !v)}
      >
        <Languages className="icon" aria-hidden />
      </button>
      {open && (
        <div className="menu-list add-target-list" role="menu" data-testid="add-target-list">
          <p className="menu-note">{t("player.addTargetNote")}</p>
          {targets.map((target) => (
            <button key={target.code} type="button" role="menuitem" data-testid={`add-target-${target.code}`} onClick={() => {
              setOpen(false);
              onAdd(target.code);
            }}>
              {languageLabel(target, locale)}
              {target.experimental && <span className="chip-exp">{t("targets.experimental")}</span>}
            </button>
          ))}
          {targets.some((target) => target.experimental) && (
            <p className="menu-note" data-testid="add-target-hint">
              {t("targets.experimentalHint")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
