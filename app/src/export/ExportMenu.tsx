import { ChevronDown, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { saveExport } from "../api/backend";
import type { Backend } from "../api/client";
import { type ExportItem } from "./exports";

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly items: readonly ExportItem[];
  /** Reports the outcome in the panel's status line. */
  readonly onResult: (message: string) => void;
}

export function ExportMenu({ backend, projectId, items, onResult }: Props) {
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
      onResult(path ? `已匯出 ${path}` : "已取消匯出");
    } catch (e) {
      onResult(`匯出失敗：${e instanceof Error ? e.message : String(e)}`);
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
        匯出
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
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
