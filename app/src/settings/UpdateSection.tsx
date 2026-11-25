import { Download, RefreshCw, RotateCw } from "lucide-react";
import { useState } from "react";
import { useT } from "../i18n/I18nProvider";
import { type Checked, reasonOf, updateCheck, updateDownload, updateInstall } from "./update";

type Available = Extract<Checked, { state: "available" }>;

type Phase =
  | { readonly kind: "idle" }
  | { readonly kind: "checking" }
  | { readonly kind: "checked"; readonly result: Checked }
  | { readonly kind: "downloading"; readonly result: Available }
  | { readonly kind: "downloaded"; readonly result: Available }
  | { readonly kind: "installing" }
  | { readonly kind: "failed"; readonly reason: string };

export function UpdateSection() {
  const { t } = useT();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const busy = phase.kind === "checking" || phase.kind === "downloading" || phase.kind === "installing";

  const check = async () => {
    setPhase({ kind: "checking" });
    try {
      setPhase({ kind: "checked", result: await updateCheck(t) });
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e, t) });
    }
  };
  const download = async (result: Available) => {
    setPhase({ kind: "downloading", result });
    try {
      await updateDownload();
      setPhase({ kind: "downloaded", result });
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e, t) });
    }
  };
  const install = async () => {
    setPhase({ kind: "installing" });
    try {
      await updateInstall();
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e, t) });
    }
  };

  const available = phase.kind === "checked" && phase.result.state === "available" ? phase.result : null;
  return (
    <section className="panel" data-testid="update-section" aria-labelledby="update-title">
      <div className="panel-head">
        <div>
          <h2 id="update-title">{t("update.title")}</h2>
          <p className="muted">{t("update.hint")}</p>
        </div>
        <button type="button" className="ghost" data-testid="update-check" disabled={busy} onClick={() => void check()}>
          <RefreshCw className="icon" aria-hidden />
          {t("update.check")}
        </button>
      </div>
      <div role="status" aria-live="polite" data-testid="update-status">
        {phase.kind === "checking" && <p className="note">{t("update.checking")}</p>}
        {phase.kind === "checked" && phase.result.state === "upToDate" && (
          <p className="note ok" data-testid="update-uptodate">
            {phase.result.current ? t("update.upToDateVersion", { version: phase.result.current }) : t("update.upToDate")}
          </p>
        )}
        {available && (
          <div className="note" data-testid="update-available">
            <p>
              {available.current ? t("update.availableFrom", { version: available.version, current: available.current }) : t("update.available", { version: available.version })}
            </p>
            {available.notes && <p className="muted">{available.notes}</p>}
            <button type="button" className="primary" data-testid="update-download" onClick={() => void download(available)}>
              <Download className="icon" aria-hidden />
              {t("update.download")}
            </button>
          </div>
        )}
        {phase.kind === "downloading" && <p className="note">{t("update.downloading", { version: phase.result.version })}</p>}
        {phase.kind === "downloaded" && (
          <div className="note ok" data-testid="update-downloaded">
            <p>{t("update.downloaded", { version: phase.result.version })}</p>
            <button type="button" className="primary" data-testid="update-install" onClick={() => void install()}>
              <RotateCw className="icon" aria-hidden />
              {t("update.install")}
            </button>
          </div>
        )}
        {phase.kind === "installing" && <p className="note">{t("update.installing")}</p>}
        {phase.kind === "failed" && (
          <p className="note bad" role="alert" data-testid="update-failed">
            {phase.reason}
          </p>
        )}
      </div>
    </section>
  );
}
