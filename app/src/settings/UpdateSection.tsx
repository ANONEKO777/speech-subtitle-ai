import { Download, RefreshCw, RotateCw } from "lucide-react";
import { useState } from "react";
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
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const busy = phase.kind === "checking" || phase.kind === "downloading" || phase.kind === "installing";

  const check = async () => {
    setPhase({ kind: "checking" });
    try {
      setPhase({ kind: "checked", result: await updateCheck() });
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e) });
    }
  };
  const download = async (result: Available) => {
    setPhase({ kind: "downloading", result });
    try {
      await updateDownload();
      setPhase({ kind: "downloaded", result });
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e) });
    }
  };
  const install = async () => {
    setPhase({ kind: "installing" });
    try {
      await updateInstall();
    } catch (e) {
      setPhase({ kind: "failed", reason: reasonOf(e) });
    }
  };

  const available = phase.kind === "checked" && phase.result.state === "available" ? phase.result : null;
  return (
    <section className="panel" data-testid="update-section" aria-labelledby="update-title">
      <div className="panel-head">
        <div>
          <h2 id="update-title">檢查更新</h2>
          <p className="muted">只在你按下按鈕時才連線檢查。模型與設定不會因為更新而重新下載。</p>
        </div>
        <button type="button" className="ghost" data-testid="update-check" disabled={busy} onClick={() => void check()}>
          <RefreshCw className="icon" aria-hidden />
          檢查更新
        </button>
      </div>
      <div role="status" aria-live="polite" data-testid="update-status">
        {phase.kind === "checking" && <p className="note">正在檢查更新…</p>}
        {phase.kind === "checked" && phase.result.state === "upToDate" && (
          <p className="note ok" data-testid="update-uptodate">
            已是最新版{phase.result.current && `（${phase.result.current}）`}。
          </p>
        )}
        {available && (
          <div className="note" data-testid="update-available">
            <p>
              有新版 {available.version}
              {available.current && `（目前 ${available.current}）`}。
            </p>
            {available.notes && <p className="muted">{available.notes}</p>}
            <button type="button" className="primary" data-testid="update-download" onClick={() => void download(available)}>
              <Download className="icon" aria-hidden />
              下載更新
            </button>
          </div>
        )}
        {phase.kind === "downloading" && <p className="note">正在下載 {phase.result.version}，請稍候…</p>}
        {phase.kind === "downloaded" && (
          <div className="note ok" data-testid="update-downloaded">
            <p>{phase.result.version} 已下載，簽章驗證通過。安裝時程式會關閉並重新開啟。</p>
            <button type="button" className="primary" data-testid="update-install" onClick={() => void install()}>
              <RotateCw className="icon" aria-hidden />
              安裝並重新啟動
            </button>
          </div>
        )}
        {phase.kind === "installing" && <p className="note">正在啟動安裝程式…</p>}
        {phase.kind === "failed" && (
          <p className="note bad" role="alert" data-testid="update-failed">
            {phase.reason}
          </p>
        )}
      </div>
    </section>
  );
}
