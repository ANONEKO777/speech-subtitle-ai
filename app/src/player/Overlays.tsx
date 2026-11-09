import { CircleAlert, Keyboard, X } from "lucide-react";
import type { BurnView } from "../api/library";
import { SHORTCUTS } from "./shortcuts";
import type { ToastData } from "./useToast";

export function HelpOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" data-testid="help" role="dialog" aria-label="鍵盤快捷鍵" onClick={onClose}>
      <div className="overlay-card" onClick={(e) => e.stopPropagation()}>
        <div className="overlay-head">
          <Keyboard className="icon" aria-hidden />
          <h2>鍵盤快捷鍵</h2>
          <button type="button" className="ghost icon-button" aria-label="關閉" data-testid="help-close" onClick={onClose}>
            <X className="icon" aria-hidden />
          </button>
        </div>
        <dl className="keys">
          {SHORTCUTS.map((row) => (
            <div key={row.keys} className="key-row">
              <dt>
                {row.keys.split(" ").map((part, i) =>
                  /^[/+–]$/.test(part) ? (
                    <span key={i} className="key-sep">
                      {part}
                    </span>
                  ) : (
                    <kbd key={i}>{part}</kbd>
                  ),
                )}
              </dt>
              <dd>{row.what}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

export function Toast({ toast, onClose }: { toast: ToastData | null; onClose: () => void }) {
  if (!toast) return null;
  return (
    <div className="toast" role="status" data-testid="toast" data-error={toast.error === true}>
      {toast.error && <CircleAlert className="icon" aria-hidden />}
      <span className="toast-text" data-testid="toast-text">
        {toast.text}
      </span>
      {toast.action && (
        <button
          type="button"
          className="toast-action"
          data-testid="toast-action"
          onClick={() => {
            toast.action?.run();
            onClose();
          }}
        >
          {toast.action.label}
        </button>
      )}
      <button type="button" className="ghost icon-button" aria-label="關閉" onClick={onClose}>
        <X className="icon" aria-hidden />
      </button>
    </div>
  );
}

export function BurnCard({ view, error, onCancel }: { view: BurnView | null; error: string | null; onCancel: () => void }) {
  if (view?.state !== "running" && !error) return null;
  return (
    <div className="burn-card" data-testid="burn-progress" role="status">
      <div className="burn-head">
        <span>{error ? "匯出出了問題" : "正在把字幕燒進影片"}</span>
        {view?.state === "running" && <span className="num" data-testid="burn-percent">{view.percent.toFixed(0)}%</span>}
      </div>
      {error ? (
        <p className="burn-error">{error}</p>
      ) : (
        <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={view?.percent ?? 0}>
          <div className="bar-fill" style={{ width: `${view?.percent ?? 0}%` }} />
        </div>
      )}
      {view?.state === "running" && (
        <button type="button" className="ghost" data-testid="burn-cancel" onClick={onCancel}>
          <X className="icon" aria-hidden />
          取消
        </button>
      )}
    </div>
  );
}
