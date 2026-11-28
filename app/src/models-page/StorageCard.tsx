import { FolderOpen, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { pickFolder } from "../api/backend";
import type { Backend } from "../api/client";
import { useT } from "../i18n/I18nProvider";
import { fetchInventory, fetchMove, fetchSettings, setModelsDir, startMove } from "../manage/api";
import { bytes } from "../manage/format";
import type { MoveStatus, StorageView } from "../manage/types";
import { isMacShell } from "../platform";
import { type Said, said, word } from "../i18n/notice";

type Step =
  | { readonly step: "view" }
  | { readonly step: "confirm"; readonly target: string; readonly models: number; readonly size: number };

/** The models folder: where it is, what changing it does to files already there, and the explicit move. */
export function StorageCard({ backend, onChanged }: { backend: Backend; onChanged: () => void }) {
  const { t, plural, locale } = useT();
  const [storage, setStorage] = useState<StorageView | null>(null);
  const [draft, setDraft] = useState("");
  const [step, setStep] = useState<Step>({ step: "view" });
  const [warnings, setWarnings] = useState<readonly Said[]>([]);
  const [error, setError] = useState<Said | null>(null);
  const [move, setMove] = useState<MoveStatus | null>(null);

  const load = useCallback(async () => {
    try {
      setStorage((await fetchSettings(backend)).storage);
    } catch (e) {
      setError(said(e));
    }
  }, [backend]);

  useEffect(() => {
    void load();
    void fetchMove(backend).then((m) => m.state === "running" && setMove(m), () => undefined);
  }, [backend, load]);

  const running = move?.state === "running";
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void fetchMove(backend).then((m) => {
        if (!alive) return;
        setMove(m);
        if (m.state !== "running") {
          void load();
          onChanged();
        }
      }, () => undefined);
    }, 700);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [running, backend, load, onChanged]);

  const ask = async () => {
    const target = draft.trim();
    if (target === "") return;
    setError(null);
    setWarnings([]);
    try {
      const installed = (await fetchInventory(backend)).assets.filter((a) => a.type === "model" && a.state === "installed");
      setStep({ step: "confirm", target, models: installed.length, size: installed.reduce((n, a) => n + (a.sizeOnDisk ?? 0), 0) });
    } catch (e) {
      setError(said(e));
    }
  };

  const changeOnly = async (target: string) => {
    try {
      const result = await setModelsDir(backend, target);
      setWarnings(result.warnings);
      setStep({ step: "view" });
      setDraft("");
      await load();
      onChanged();
    } catch (e) {
      setError(said(e));
      setStep({ step: "view" });
    }
  };

  const moveAll = async (target: string) => {
    if (!storage) return;
    try {
      setMove(await startMove(backend, target, storage.modelsDir));
      setStep({ step: "view" });
      setDraft("");
    } catch (e) {
      setError(said(e));
      setStep({ step: "view" });
    }
  };

  const percent = move && move.bytesTotal > 0 ? Math.round((move.bytesDone / move.bytesTotal) * 100) : 0;
  return (
    <div className="card manage-card" data-testid="storage-card">
      <h3>{t("storage.title")}</h3>
      <p className="path-big" data-testid="models-dir" title={storage?.modelsDir}>
        {storage?.modelsDir ?? "…"}
      </p>
      <p className="sub">{storage?.customModelsDir ? t("storage.custom") : t("storage.default")}</p>

      <div className="inline-form">
        <input
          className="text-input"
          data-testid="models-dir-input"
          placeholder={t(isMacShell() ? "storage.placeholder.posix" : "storage.placeholder.win")}
          value={draft}
          disabled={running}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          className="ghost"
          data-testid="models-dir-pick"
          disabled={running}
          onClick={() => void pickFolder().then((p) => p && setDraft(p), () => undefined)}
        >
          <FolderOpen className="icon" aria-hidden />
          {t("storage.pick")}
        </button>
        <button type="button" data-testid="models-dir-change" disabled={running || draft.trim() === ""} onClick={() => void ask()}>
          {t("storage.change")}
        </button>
      </div>

      {step.step === "confirm" && (
        <div className="callout warn" role="alertdialog" data-testid="models-dir-confirm">
          <TriangleAlert className="icon" aria-hidden />
          <div>
            <p>
              <strong>{t("storage.confirm.lead")}</strong>
              {plural("storage.confirm.body", step.models, { size: bytes(step.size, locale), notInstalled: t("models.state.notInstalled") })}
            </p>
            <p className="sub">{t("storage.newFolder", { target: step.target })}</p>
            <div className="dialog-buttons start">
              <button type="button" className="primary" data-testid="models-dir-move" onClick={() => void moveAll(step.target)}>
                {t("storage.move")}
              </button>
              <button type="button" data-testid="models-dir-only" onClick={() => void changeOnly(step.target)}>
                {t("storage.only")}
              </button>
              <button type="button" className="ghost" data-testid="models-dir-cancel" onClick={() => setStep({ step: "view" })}>
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {warnings.map((w) => (
        <p key={w.text} className="note warn" role="status" data-testid="models-dir-warning">
          {word(w, locale)}
        </p>
      ))}
      {error && (
        <p className="note bad" role="alert" data-testid="models-dir-error">
          {word(error, locale)}
        </p>
      )}

      {move && move.state !== "idle" && (
        <div className="move" data-testid="move-status" data-state={move.state}>
          <div className="mbar">
            <span style={{ width: `${move.state === "done" ? 100 : percent}%` }} />
          </div>
          <p className="sub">
            {move.state === "running" &&
              plural("storage.moving", move.filesTotal, { percent, filesDone: move.filesDone, done: bytes(move.bytesDone, locale), total: bytes(move.bytesTotal, locale) })}
            {move.state === "done" && plural("storage.moved", move.filesTotal, { size: bytes(move.bytesTotal, locale), target: move.target ?? "" })}
            {move.state === "failed" && t("storage.moveFailed", { error: move.error ? word(move.error, locale) : "" })}
          </p>
          {move.warnings.map((w) => (
            <p key={w.text} className="note warn">
              {word(w, locale)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
