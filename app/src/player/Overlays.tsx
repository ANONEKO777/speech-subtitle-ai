import { CircleAlert, Keyboard, X } from "lucide-react";
import type { BurnView } from "../api/library";
import { useT } from "../i18n/I18nProvider";
import { SHORTCUTS } from "./shortcuts";
import type { ToastData } from "./useToast";

export function HelpOverlay({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  return (
    <div className="overlay" data-testid="help" role="dialog" aria-label={t("player.help.title")} onClick={onClose}>
      <div className="overlay-card" onClick={(e) => e.stopPropagation()}>
        <div className="overlay-head">
          <Keyboard className="icon" aria-hidden />
          <h2>{t("player.help.title")}</h2>
          <button type="button" className="ghost icon-button" aria-label={t("common.close")} data-testid="help-close" onClick={onClose}>
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
              <dd>{t(row.what)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

export function Toast({ toast, onClose }: { toast: ToastData | null; onClose: () => void }) {
  const { t } = useT();
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
      <button type="button" className="ghost icon-button" aria-label={t("common.close")} onClick={onClose}>
        <X className="icon" aria-hidden />
      </button>
    </div>
  );
}

export function BurnCard({ view, error, onCancel }: { view: BurnView | null; error: string | null; onCancel: () => void }) {
  const { t } = useT();
  if (view?.state !== "running" && !error) return null;
  return (
    <div className="burn-card" data-testid="burn-progress" role="status">
      <div className="burn-head">
        <span>{error ? t("player.burn.problem") : t("player.burn.title")}</span>
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
          {t("common.cancel")}
        </button>
      )}
    </div>
  );
}
