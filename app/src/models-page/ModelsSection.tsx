import { CircleAlert, Download, HardDriveDownload, RefreshCw, RotateCcw, ShieldCheck, Trash2, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type Backend, ApiError } from "../api/client";
import {
  cancelDownload,
  checkUpdates,
  fetchInventory,
  redownload,
  refusalOf,
  repairAsset,
  startAsset,
  updateAsset,
  verifyAsset,
} from "../manage/api";
import { fraction, isActive, stateLabel } from "../manage/downloads";
import { bytes, shortVersion, speed } from "../manage/format";
import { LOCAL_BUILD_ELSEWHERE_NO_UPDATE_TEXT, LOCAL_BUILD_ELSEWHERE_TEXT, LOCAL_BUILD_NO_UPDATE_TEXT, LOCAL_BUILD_TEXT } from "../manage/localBuild";
import type { Downloads } from "../manage/useDownloads";
import type { Asset, DownloadJob, Inventory, UpdateReport } from "../manage/types";
import { DeleteDialog } from "./DeleteDialog";
import { type RowAction, rowActions, shaText, stateText } from "./rules";

interface Note {
  readonly text: string;
  readonly bad: boolean;
}

const ACTION_TEXT: Record<RowAction, string> = {
  download: "下載",
  resume: "續傳",
  verify: "驗證",
  repair: "修復",
  redownload: "重新下載",
  update: "更新",
  delete: "刪除",
  cancel: "取消下載",
};

const ACTION_ICON: Record<RowAction, typeof Download> = {
  download: Download,
  resume: Download,
  verify: ShieldCheck,
  repair: Wrench,
  redownload: RotateCcw,
  update: HardDriveDownload,
  delete: Trash2,
  cancel: X,
};

export function ModelsSection({ backend, downloads }: { backend: Backend; downloads: Downloads }) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlyMap<string, string>>(new Map());
  const [notes, setNotes] = useState<ReadonlyMap<string, Note>>(new Map());
  const [updates, setUpdates] = useState<UpdateReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [deleting, setDeleting] = useState<Asset | null>(null);

  const reload = useCallback(async () => {
    try {
      setInventory(await fetchInventory(backend));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [backend]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const endedKey = downloads.list.filter((j) => !isActive(j)).map((j) => `${j.id}:${j.state}`).join(",");
  useEffect(() => {
    void reload();
  }, [endedKey, reload]);

  const setNote = (id: string, note: Note | null) =>
    setNotes((prev) => {
      const next = new Map(prev);
      if (note) next.set(id, note);
      else next.delete(id);
      return next;
    });
  const setWorking = (id: string, label: string | null) =>
    setBusy((prev) => {
      const next = new Map(prev);
      if (label) next.set(id, label);
      else next.delete(id);
      return next;
    });

  const act = async (asset: Asset, action: RowAction, job: DownloadJob | undefined) => {
    if (action === "delete") {
      setDeleting(asset);
      return;
    }
    setNote(asset.id, null);
    setWorking(asset.id, `${ACTION_TEXT[action]}中…`);
    try {
      switch (action) {
        case "download":
        case "resume":
          await startAsset(backend, asset);
          break;
        case "redownload":
          await redownload(backend, asset.id);
          break;
        case "update":
          await updateAsset(backend, asset.id);
          break;
        case "cancel":
          if (job) await cancelDownload(backend, job.id);
          break;
        case "verify": {
          await verifyAsset(backend, asset.id);
          const fresh = (await fetchInventory(backend)).assets.find((a) => a.id === asset.id);
          setNote(asset.id, { text: fresh?.shaState === "verified" ? "SHA256 相符，檔案完整" : "SHA256 不符，請按「修復」", bad: fresh?.shaState !== "verified" });
          break;
        }
        case "repair": {
          const r = await repairAsset(backend, asset.id);
          setNote(asset.id, { text: `修復：${r.action}${r.reason ? `（${r.reason}）` : ""}`, bad: false });
          break;
        }
      }
      downloads.refresh();
      await reload();
    } catch (e) {
      const r = refusalOf(e);
      setNote(asset.id, { text: [r.message, ...r.blockers].join("；"), bad: true });
    } finally {
      setWorking(asset.id, null);
    }
  };

  const check = async () => {
    setChecking(true);
    try {
      setUpdates(await checkUpdates(backend));
      setError(null);
    } catch (e) {
      setUpdates(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  const updateOf = (id: string) => updates?.items.find((i) => i.id === id);
  const installed = inventory?.assets.filter((a) => a.state === "installed") ?? [];

  return (
    <section className="panel" data-testid="models-section" aria-labelledby="models-title">
      <div className="panel-head">
        <div>
          <h2 id="models-title">模型與執行環境</h2>
          <p className="muted" data-testid="inv-summary">
            {inventory ? `已安裝 ${installed.length} 項，共 ${bytes(inventory.installedBytes)}。` : "正在讀取…"}
            模型和執行檔另外下載，可以在這裡刪除、驗證、修復或重新下載。
          </p>
        </div>
        <div className="panel-actions">
          <button type="button" data-testid="check-updates" disabled={checking} onClick={() => void check()}>
            <RefreshCw className={checking ? "icon spin" : "icon"} aria-hidden />
            檢查更新
          </button>
        </div>
      </div>

      {error && (
        <p className="note bad" role="alert" data-testid="inv-error">
          <CircleAlert className="icon" aria-hidden />
          {error}
        </p>
      )}
      {updates && (
        <p className="note" data-testid="update-message">
          {updates.message}
        </p>
      )}

      {inventory && (
        <div className="table-wrap">
          <table className="inv" data-testid="inv-table">
            <thead>
              <tr>
                <th>名稱</th>
                <th>狀態</th>
                <th>版本</th>
                <th>大小</th>
                <th>使用於</th>
                <th>相依</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {inventory.assets.map((asset) => {
                const job = downloads.byAsset.get(asset.id);
                const live = job && isActive(job) ? job : undefined;
                const working = busy.get(asset.id);
                const note = notes.get(asset.id);
                const update = updateOf(asset.id);
                const actions = rowActions(asset, job, update);
                return (
                  <tr key={asset.id} data-testid={`inv-${asset.id}`} data-state={asset.state} data-sha={asset.shaState}>
                    <td className="name-cell">
                      <span className="asset-id">{asset.id}</span>
                      <span className="sub">
                        {asset.type === "model" ? "模型" : "執行檔"} · {asset.kind} · {asset.license}
                      </span>
                      {asset.localBuild && asset.state === "not_installed" && (
                        <span className="sub" data-testid={`inv-${asset.id}-build`}>
                          {LOCAL_BUILD_TEXT}
                        </span>
                      )}
                      {asset.path && asset.state !== "not_installed" && (
                        <span className="sub path-line" title={asset.path}>
                          {asset.path}
                        </span>
                      )}
                      {asset.foundOutsideRuntimes && (
                        <span className="sub" data-testid={`inv-${asset.id}-elsewhere`}>
                          {LOCAL_BUILD_ELSEWHERE_TEXT}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="chip-state" data-state={asset.state} data-testid={`inv-${asset.id}-state`}>
                        {stateText(asset)}
                      </span>
                      <span className="sub" data-testid={`inv-${asset.id}-sha`}>
                        {shaText(asset)}
                      </span>
                      {live && (
                        <div className="inline-job" data-testid={`inv-${asset.id}-job`}>
                          <div className="mbar">
                            <span style={{ width: `${Math.round(fraction(live) * 100)}%` }} />
                          </div>
                          <span className="sub" data-testid={`inv-${asset.id}-progress`}>
                            {stateLabel(live)} {Math.round(fraction(live) * 100)}% · {bytes(live.bytesDone)} / {bytes(live.bytesTotal)} ·{" "}
                            {speed(live.speedBps)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td>
                      <span data-testid={`inv-${asset.id}-version`} title={asset.installedVersion ?? undefined}>
                        {asset.installedVersion ? shortVersion(asset.installedVersion) : asset.state === "installed" ? "未記錄" : "—"}
                      </span>
                      <span className="sub" title={asset.version}>
                        登錄版本 {shortVersion(asset.version)}
                      </span>
                      {update && update.status !== "not_installed" && (
                        <span className={`sub ${update.status === "update_available" ? "ok" : ""}`} data-testid={`inv-${asset.id}-update`} title={update.message}>
                          {asset.localBuild
                            ? asset.foundOutsideRuntimes
                              ? LOCAL_BUILD_ELSEWHERE_NO_UPDATE_TEXT
                              : LOCAL_BUILD_NO_UPDATE_TEXT
                            : update.status === "update_available"
                              ? update.installable
                                ? "有新版"
                                : "有新版（需更新 App）"
                              : "已是最新"}
                        </span>
                      )}
                    </td>
                    <td>
                      <span>{asset.localBuild && asset.sizeOnDisk === null ? "—" : bytes(asset.sizeOnDisk ?? asset.sizeBytes)}</span>
                      {asset.sizeOnDisk === null && !asset.localBuild && <span className="sub">下載大小</span>}
                    </td>
                    <td>
                      <span className="chips">
                        {asset.usedByProfiles.length === 0 && <span className="sub">—</span>}
                        {asset.usedByProfiles.map((p) => (
                          <span key={p} className="chip-tag">
                            {p}
                          </span>
                        ))}
                      </span>
                      {asset.inActiveProfile && (
                        <span className="sub ok" data-testid={`inv-${asset.id}-active`}>
                          目前使用
                        </span>
                      )}
                    </td>
                    <td data-testid={`inv-${asset.id}-deps`}>
                      {asset.dependents.length === 0 && <span className="sub">—</span>}
                      {asset.dependents.map((d) => (
                        <span key={d.id} className="sub dep" data-installed={d.installed}>
                          {d.id}
                          {d.installed ? "（已安裝）" : ""}
                        </span>
                      ))}
                    </td>
                    <td className="actions-cell">
                      <div className="row-actions">
                        {actions.map((action) => {
                          const Icon = ACTION_ICON[action];
                          return (
                            <button
                              key={action}
                              type="button"
                              className={action === "delete" ? "ghost danger-text" : "ghost"}
                              data-testid={`act-${asset.id}-${action}`}
                              disabled={working !== undefined}
                              onClick={() => void act(asset, action, job)}
                            >
                              <Icon className="icon" aria-hidden />
                              {ACTION_TEXT[action]}
                            </button>
                          );
                        })}
                      </div>
                      {working && <span className="sub">{working}</span>}
                      {note && (
                        <span className={`sub note-line ${note.bad ? "bad" : "ok"}`} role={note.bad ? "alert" : "status"} data-testid={`inv-${asset.id}-note`}>
                          {note.text}
                        </span>
                      )}
                      {!note && job?.failure && !live && (
                        <span className="sub note-line bad" role="alert" data-testid={`inv-${asset.id}-note`}>
                          {job.failure.message}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {deleting && (
        <DeleteDialog
          backend={backend}
          asset={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            downloads.refresh();
            void reload();
          }}
        />
      )}
    </section>
  );
}
