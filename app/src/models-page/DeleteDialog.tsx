import { TriangleAlert, X } from "lucide-react";
import { useReducer, useState } from "react";
import type { Backend } from "../api/client";
import { deleteAsset, refusalOf } from "../manage/api";
import { bytes } from "../manage/format";
import type { Asset } from "../manage/types";
import { type DeleteStep, forceReasonError, reduceDelete } from "./rules";

interface Props {
  readonly backend: Backend;
  readonly asset: Asset;
  readonly onClose: () => void;
  readonly onDeleted: () => void;
}

/** Deletes one asset. A refusal lists its blockers, and force needs a reason of at least 8 characters. */
export function DeleteDialog({ backend, asset, onClose, onDeleted }: Props) {
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

  const reasonError = state.step === "force" ? forceReasonError(state.reason) : null;
  return (
    <div className="modal" role="dialog" aria-label={`刪除 ${asset.id}`} data-testid="delete-dialog">
      <div className="modal-card manage-dialog">
        <div className="dialog-head">
          <TriangleAlert className="icon warn" aria-hidden />
          <h2>刪除 {asset.id}</h2>
          <button type="button" className="ghost icon-button" aria-label="關閉" onClick={onClose}>
            <X className="icon" aria-hidden />
          </button>
        </div>

        {state.step === "confirm" && (
          <>
            <p>
              會從磁碟移除{asset.sizeOnDisk !== null ? ` ${bytes(asset.sizeOnDisk)}` : ""}
              {asset.path ? `（${asset.path}）` : ""}。之後可以再下載。
            </p>
            {asset.blockers.length > 0 && (
              <p className="note warn" data-testid="delete-prewarn">
                注意：{asset.blockers.join("；")}
              </p>
            )}
          </>
        )}

        {state.step === "refused" && (
          <div data-testid="delete-refused">
            <p className="note bad" role="alert" data-testid="delete-message">
              {state.refusal.message}
            </p>
            {state.refusal.blockers.length > 0 && (
              <ul className="blockers" data-testid="delete-blockers">
                {state.refusal.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {state.refusal.canForce ? (
              <p className="muted">仍要刪除的話，可以強制刪除。強制刪除要寫下原因，原因會記在日誌。</p>
            ) : (
              <p className="muted">這個項目現在不能刪除。</p>
            )}
          </div>
        )}

        {state.step === "force" && (
          <div data-testid="delete-force">
            <p className="note bad">{state.refusal.message}</p>
            {state.refusal.blockers.length > 0 && (
              <ul className="blockers">
                {state.refusal.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            <label className="field-label" htmlFor="force-reason">
              強制刪除的原因（至少 8 個字）
            </label>
            <input
              id="force-reason"
              className="text-input"
              data-testid="force-reason"
              value={state.reason}
              placeholder="例如：要換成新版重新下載"
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
            {state.message}
          </p>
        )}

        <div className="dialog-buttons">
          <button type="button" className="ghost" data-testid="delete-cancel" onClick={onClose}>
            {state.step === "failed" ? "關閉" : "取消"}
          </button>
          {state.step === "confirm" && (
            <button type="button" className="danger" data-testid="delete-confirm" disabled={busy} onClick={() => void run()}>
              刪除
            </button>
          )}
          {state.step === "refused" && state.refusal.canForce && (
            <button type="button" className="danger" data-testid="delete-want-force" onClick={() => dispatch({ type: "wantForce" })}>
              強制刪除…
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
              強制刪除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
