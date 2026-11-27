import { ChevronDown, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { saveExport } from "../api/backend";
import type { Backend } from "../api/client";
import { useT } from "../i18n/I18nProvider";
import { type ExportItem, NoSummary } from "./exports";
import { said, word } from "../i18n/notice";

/** A menu entry that starts something instead of saving a file. */
export interface ExportAction {
  readonly id: string;
  readonly label: string;
  readonly run: () => void;
  readonly disabled?: boolean;
}

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly items: readonly ExportItem[];
  readonly actions?: readonly ExportAction[];
  /** Reports the outcome in the panel's status line. */
  readonly onResult: (message: string) => void;
}

export function ExportMenu({ backend, projectId, items, actions = [], onResult }: Props) {
  const { t, locale } = useT();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [open]);

  const run = async (item: ExportItem) => {
    setOpen(false);
    setBusy(true);
    try {
      const path = await saveExport(item.file, await item.text(backend, projectId));
      onResult(path ? t("export.done", { path }) : t("export.cancelled"));
    } catch (e) {
      const reason = e instanceof NoSummary ? t("export.noSummary") : word(said(e), locale);
      onResult(t("export.failed", { reason }));
    } finally {
      setBusy(false);
    }
  };

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
        className="ghost menu-button"
        data-testid="export-menu"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
      >
        <Download className="icon" aria-hidden />
        {t("export.button")}
        <ChevronDown className="icon chevron" aria-hidden />
      </button>
      {open && (
        <div className="menu-list" role="menu" data-testid="export-list">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              data-testid={`export-${item.id}`}
              autoFocus={item === items[0]}
              onClick={() => void run(item)}
            >
              {item.label(t)}
            </button>
          ))}
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              role="menuitem"
              data-testid={`export-${action.id}`}
              disabled={action.disabled}
              onClick={() => {
                setOpen(false);
                action.run();
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
