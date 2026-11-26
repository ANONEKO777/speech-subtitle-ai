import { CircleAlert, Download, HardDriveDownload, RefreshCw, RotateCcw, ShieldCheck, Trash2, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type Backend, ApiError } from "../api/client";
import type { Translate } from "../i18n";
import { useT } from "../i18n/I18nProvider";
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
import { localBuildElsewhereNoUpdateText, localBuildElsewhereText, localBuildNoUpdateText, localBuildText } from "../manage/localBuild";
import type { Downloads } from "../manage/useDownloads";
import type { Asset, DownloadJob, Inventory, UpdateReport } from "../manage/types";
import { DeleteDialog } from "./DeleteDialog";
import { type RowAction, rowActions, shaText, stateText } from "./rules";

/** What a row action left to say. Kept as data and worded at render, so a language switch re-words it. */
type Note =
  | { readonly kind: "verified"; readonly ok: boolean }
  | { readonly kind: "repaired"; readonly action: string; readonly reason: string }
  | { readonly kind: "refused"; readonly message: string; readonly blockers: readonly string[] };

type Working = Exclude<RowAction, "delete">;

const isBad = (note: Note): boolean => (note.kind === "verified" ? !note.ok : note.kind === "refused");

function noteText(note: Note, t: Translate): string {
  switch (note.kind) {
    case "verified":
      return note.ok ? t("models.verify.ok") : t("models.verify.bad", { repair: t("models.action.repair") });
    case "repaired":
      return note.reason ? t("models.repaired.reason", { action: note.action, reason: note.reason }) : t("models.repaired", { action: note.action });
    case "refused":
      return [note.message, ...note.blockers].join(t("models.blockerSeparator"));
  }
}

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
  const { t, plural, locale } = useT();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlyMap<string, Working>>(new Map());
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
  const setWorking = (id: string, action: Working | null) =>
    setBusy((prev) => {
      const next = new Map(prev);
      if (action) next.set(id, action);
      else next.delete(id);
      return next;
    });

  const act = async (asset: Asset, action: RowAction, job: DownloadJob | undefined) => {
    if (action === "delete") {
      setDeleting(asset);
      return;
    }
    setNote(asset.id, null);
    setWorking(asset.id, action);
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
          setNote(asset.id, { kind: "verified", ok: fresh?.shaState === "verified" });
          break;
        }
        case "repair": {
          const r = await repairAsset(backend, asset.id);
          setNote(asset.id, { kind: "repaired", action: r.action, reason: r.reason });
          break;
        }
      }
      downloads.refresh();
      await reload();
    } catch (e) {
      const r = refusalOf(e);
      setNote(asset.id, { kind: "refused", message: r.message, blockers: r.blockers });
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
          <h2 id="models-title">{t("models.title")}</h2>
          <p className="muted" data-testid="inv-summary">
            {inventory ? plural("models.summary", installed.length, { size: bytes(inventory.installedBytes, locale) }) : t("models.summary.loading")}
          </p>
        </div>
        <div className="panel-actions">
          <button type="button" data-testid="check-updates" disabled={checking} onClick={() => void check()}>
            <RefreshCw className={checking ? "icon spin" : "icon"} aria-hidden />
            {t("models.checkUpdates")}
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
                <th>{t("models.col.name")}</th>
                <th>{t("models.col.status")}</th>
                <th>{t("models.col.version")}</th>
                <th>{t("models.col.size")}</th>
                <th>{t("models.col.usedBy")}</th>
                <th>{t("models.col.neededBy")}</th>
                <th className="actions-cell">{t("models.col.actions")}</th>
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
                        {asset.type === "model" ? t("asset.model") : t("asset.program")} · {asset.kind} · {asset.license}
                      </span>
                      {asset.localBuild && asset.state === "not_installed" && (
                        <span className="sub" data-testid={`inv-${asset.id}-build`}>
                          {localBuildText(t)}
                        </span>
                      )}
                      {asset.path && asset.state !== "not_installed" && (
                        <span className="sub path-line" title={asset.path}>
                          {asset.path}
                        </span>
                      )}
                      {asset.foundOutsideRuntimes && (
                        <span className="sub" data-testid={`inv-${asset.id}-elsewhere`}>
                          {localBuildElsewhereText(t)}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="chip-state" data-state={asset.state} data-testid={`inv-${asset.id}-state`}>
                        {stateText(asset, t)}
                      </span>
                      <span className="sub" data-testid={`inv-${asset.id}-sha`}>
                        {shaText(asset, t)}
                      </span>
                      {live && (
                        <div className="inline-job" data-testid={`inv-${asset.id}-job`}>
                          <div className="mbar">
                            <span style={{ width: `${Math.round(fraction(live) * 100)}%` }} />
                          </div>
                          <span className="sub" data-testid={`inv-${asset.id}-progress`}>
                            {stateLabel(live, t)} {Math.round(fraction(live) * 100)}% · {bytes(live.bytesDone, locale)} / {bytes(live.bytesTotal, locale)} ·{" "}
                            {speed(live.speedBps, locale)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td>
                      <span data-testid={`inv-${asset.id}-version`} title={asset.installedVersion ?? undefined}>
                        {asset.installedVersion ? shortVersion(asset.installedVersion) : asset.state === "installed" ? t("models.versionUnrecorded") : "—"}
                      </span>
                      <span className="sub" title={asset.version}>
                        {t("models.registryVersion", { version: shortVersion(asset.version) })}
                      </span>
                      {update && update.status !== "not_installed" && (
                        <span className={`sub ${update.status === "update_available" ? "ok" : ""}`} data-testid={`inv-${asset.id}-update`} title={update.message}>
                          {asset.localBuild
                            ? asset.foundOutsideRuntimes
                              ? localBuildElsewhereNoUpdateText(t)
                              : localBuildNoUpdateText(t)
                            : update.status === "update_available"
                              ? update.installable
                                ? t("models.update.available")
                                : t("models.update.needsApp")
                              : t("models.update.current")}
                        </span>
                      )}
                    </td>
                    <td>
                      <span>{asset.localBuild && asset.sizeOnDisk === null ? "—" : bytes(asset.sizeOnDisk ?? asset.sizeBytes, locale)}</span>
                      {asset.sizeOnDisk === null && !asset.localBuild && <span className="sub">{t("models.downloadSize")}</span>}
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
                          {t("models.inActiveProfile")}
                        </span>
                      )}
                    </td>
                    <td data-testid={`inv-${asset.id}-deps`}>
                      {asset.dependents.length === 0 && <span className="sub">—</span>}
                      {asset.dependents.map((d) => (
                        <span key={d.id} className="sub dep" data-installed={d.installed}>
                          {d.installed ? t("models.dep.installed", { id: d.id }) : d.id}
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
                              {t(`models.action.${action}`)}
                            </button>
                          );
                        })}
                      </div>
                      {working && <span className="sub">{t(`models.working.${working}`)}</span>}
                      {note && (
                        <span className={`sub note-line ${isBad(note) ? "bad" : "ok"}`} role={isBad(note) ? "alert" : "status"} data-testid={`inv-${asset.id}-note`}>
                          {noteText(note, t)}
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
