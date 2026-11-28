import { TriangleAlert, X } from "lucide-react";
import { useReducer, useState } from "react";
import type { Backend } from "../api/client";
import type { Translate } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import { deleteAsset, refusalOf } from "../manage/api";
import { bytes } from "../manage/format";
import type { Asset } from "../manage/types";
import { MIN_REASON, type DeleteStep, forceReasonError, reduceDelete } from "./rules";
import { word } from "../i18n/notice";

interface Props {
  readonly backend: Backend;
  readonly asset: Asset;
  readonly onClose: () => void;
  readonly onDeleted: () => void;
}

function confirmText(asset: Asset, t: Translate, locale: Locale): string {
  const size = asset.sizeOnDisk !== null ? bytes(asset.sizeOnDisk, locale) : null;
  if (size !== null && asset.path) return t("delete.confirm.sizePath", { size, path: asset.path });
  if (size !== null) return t("delete.confirm.size", { size });
  if (asset.path) return t("delete.confirm.path", { path: asset.path });
  return t("delete.confirm.plain");
}

/** Deletes one asset. A refusal lists its blockers, and force needs a reason of at least 8 characters. */
export function DeleteDialog({ backend, asset, onClose, onDeleted }: Props) {
  const { t, locale } = useT();
  const [state, dispatch] = useReducer(reduceDelete, { step: "confirm" } as DeleteStep);
  const [busy, setBusy] = useState(false);

  const run = async (reason?: string) => {
    setBusy(true);
    try {
      await deleteAsset(backend, asset, reason === undefined ? undefined : { reason: reason.trim() });
      onDeleted();
    } catch (e) {
      const refusal = refusalOf(e);
      dispatch(state.step === "force" ? { type: "failed", message: refusal.message } : { type: "refused", refusal });
    } finally {
      setBusy(false);
    }
  };

  const reasonError = state.step === "force" ? forceReasonError(state.reason, t) : null;
  return (
    <div className="modal" role="dialog" aria-label={t("delete.title", { id: asset.id })} data-testid="delete-dialog">
      <div className="modal-card manage-dialog">
        <div className="dialog-head">
          <TriangleAlert className="icon warn" aria-hidden />
          <h2>{t("delete.title", { id: asset.id })}</h2>
          <button type="button" className="ghost icon-button" aria-label={t("common.close")} onClick={onClose}>
            <X className="icon" aria-hidden />
          </button>
        </div>

        {state.step === "confirm" && (
          <>
            <p>{confirmText(asset, t, locale)}</p>
            {asset.blockers.length > 0 && (
              <p className="note warn" data-testid="delete-prewarn">
                {t("delete.warn", { blockers: asset.blockers.map((b) => word(b, locale)).join(t("models.blockerSeparator")) })}
              </p>
            )}
          </>
        )}

        {state.step === "refused" && (
          <div data-testid="delete-refused">
            <p className="note bad" role="alert" data-testid="delete-message">
              {word(state.refusal.message, locale)}
            </p>
            {state.refusal.blockers.length > 0 && (
              <ul className="blockers" data-testid="delete-blockers">
                {state.refusal.blockers.map((b) => (
                  <li key={b.text}>{word(b, locale)}</li>
                ))}
              </ul>
            )}
            {state.refusal.canForce ? (
              <p className="muted">{t("delete.canForce")}</p>
            ) : (
              <p className="muted">{t("delete.cannot")}</p>
            )}
          </div>
        )}

        {state.step === "force" && (
          <div data-testid="delete-force">
            <p className="note bad">{word(state.refusal.message, locale)}</p>
            {state.refusal.blockers.length > 0 && (
              <ul className="blockers">
                {state.refusal.blockers.map((b) => (
                  <li key={b.text}>{word(b, locale)}</li>
                ))}
              </ul>
            )}
            <label className="field-label" htmlFor="force-reason">
              {t("delete.reasonLabel", { min: MIN_REASON })}
            </label>
            <input
              id="force-reason"
              className="text-input"
              data-testid="force-reason"
              value={state.reason}
              placeholder={t("delete.reasonPlaceholder")}
              onChange={(e) => dispatch({ type: "reason", text: e.target.value })}
              autoFocus
            />
            {state.reason !== "" && reasonError && (
              <p className="note warn" data-testid="force-reason-error">
                {reasonError}
              </p>
            )}
          </div>
        )}

        {state.step === "failed" && (
          <p className="note bad" role="alert" data-testid="delete-failed">
            {word(state.message, locale)}
          </p>
        )}

        <div className="dialog-buttons">
          <button type="button" className="ghost" data-testid="delete-cancel" onClick={onClose}>
            {state.step === "failed" ? t("common.close") : t("common.cancel")}
          </button>
          {state.step === "confirm" && (
            <button type="button" className="danger" data-testid="delete-confirm" disabled={busy} onClick={() => void run()}>
              {t("models.action.delete")}
            </button>
          )}
          {state.step === "refused" && state.refusal.canForce && (
            <button type="button" className="danger" data-testid="delete-want-force" onClick={() => dispatch({ type: "wantForce" })}>
              {t("delete.forceAsk")}
            </button>
          )}
          {state.step === "force" && (
            <button
              type="button"
              className="danger"
              data-testid="force-confirm"
              disabled={busy || reasonError !== null}
              onClick={() => void run(state.reason)}
            >
              {t("delete.force")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
