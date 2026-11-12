import { Captions, Film, Home, Layers, ListPlus, LoaderCircle, Settings, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_SOURCE, SOURCE_NOTES, type SourceLang, sourceLabel } from "./api/sourceLang";
import { type BackendStatus, allowVideo, watchBackend, watchDrops } from "./api/backend";
import {
  ApiError,
  type Backend,
  type LanguageInfo,
  type LanguageSet,
  cancelJob,
  createProject,
  fetchCues,
  fetchEditedIds,
  fetchLanguageSet,
  fetchLanguages,
  fetchProject,
  startJob,
} from "./api/client";
import { AddDialog, rowsFor } from "./batch/AddDialog";
import { type AddEntry, cancelPower } from "./batch/api";
import { BatchPanel } from "./batch/BatchPanel";
import { CountdownModal } from "./batch/CountdownModal";
import { type BatchItem, formatEta, overall } from "./batch/model";
import { notifyWindows } from "./batch/notify";
import { classifyPath } from "./batch/paths";
import { useBatch } from "./batch/useBatch";
import { type LibraryItem, NO_PLAYBACK, type Playback, fetchLibrary, fetchPlayback } from "./api/library";
import type { Loaded } from "./editor/useCueEditing";
import { shortName } from "./export/exports";
import { ImportPanel, SourcePick } from "./import/ImportPanel";
import { Library } from "./player/Library";
import { Toast } from "./player/Overlays";
import { Player } from "./player/Player";
import { useToast } from "./player/useToast";
import { QUEUE_KEY, dequeue, enqueue, neighbour, parseQueue, playing, pruned } from "./player/queue";
import { ProgressBar } from "./progress/ProgressBar";
import type { EditsReport } from "./progress/job";
import { useJob } from "./progress/useJob";
import { fetchModelStates } from "./manage/api";
import { SettingsPage } from "./settings/SettingsPage";
import { SettingsBar } from "./settings/SettingsBar";
import { SKIPPED_KEY, needsWizard } from "./wizard/firstRun";
import { Wizard } from "./wizard/Wizard";
import { LinkedText } from "./manage/LinkedText";
import { KEY, parseSettings } from "./settings/settings";

type Screen =
  | { readonly kind: "idle"; readonly error?: string }
  | { readonly kind: "settings" }
  | { readonly kind: "importing"; readonly videoPath: string; readonly projectId: string; readonly jobId: string }
  | {
      readonly kind: "playing";
      readonly videoPath: string;
      readonly projectId: string;
      readonly sourceLang: SourceLang;
      /** The languages the project has a finished translation for. */
      readonly languages: readonly LanguageInfo[];
      readonly lang: string;
      readonly loaded: Loaded;
      readonly playback: Playback;
      readonly notice: string | null;
    };

const editsNotice = ({ kept, unmatched }: EditsReport): string | null => {
  const parts = [
    kept > 0 ? `重新翻譯後已保留 ${kept} 條手動修改` : "",
    unmatched > 0 ? `${unmatched} 條修改因原文已變而沒有套用，仍存在專案資料夾的 edits 檔` : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join("；") : null;
};

const playingName = (screen: Extract<Screen, { kind: "playing" }>) =>
  screen.languages.find((l) => l.code === screen.lang)?.nativeName ?? screen.lang;

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const fileName = (path: string) => path.slice(Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) + 1);

function Importing({
  backend,
  screen,
  onDone,
  onStop,
}: {
  backend: Backend;
  screen: Extract<Screen, { kind: "importing" }>;
  onDone: (edits: EditsReport) => void;
  onStop: (error?: string) => void;
}) {
  const view = useJob(backend, screen.jobId);
  useEffect(() => {
    if (view.kind === "done") onDone(view.edits);
    if (view.kind === "failed") onStop(`處理失敗：${view.error}`);
    if (view.kind === "cancelled") onStop();
  }, [view, onDone, onStop]);
  return (
    <section className="importing" data-testid="importing">
      <div className="card importing-card">
        <div className="importing-head">
          <span className="badge-icon">
            <Film aria-hidden />
          </span>
          <div className="importing-title">
            <span className="eyebrow">正在處理</span>
            <h2>{fileName(screen.videoPath)}</h2>
            <span className="path">{screen.videoPath}</span>
          </div>
        </div>
        <ProgressBar view={view} />
        <button type="button" className="ghost" onClick={() => void cancelJob(backend, screen.jobId)}>
          <X className="icon" aria-hidden />
          取消
        </button>
      </div>
    </section>
  );
}

export function App() {
  const [status, setStatus] = useState<BackendStatus>({ kind: "starting" });
  const [screen, setScreen] = useState<Screen>({ kind: "idle" });
  const [settings, setSettings] = useState(() => parseSettings(localStorage.getItem(KEY)));
  const [queue, setQueue] = useState(() => parseQueue(localStorage.getItem(QUEUE_KEY)));
  const [library, setLibrary] = useState<readonly LibraryItem[]>([]);
  const [languageNames, setLanguageNames] = useState<ReadonlyMap<string, string>>(new Map());
  const [dropping, setDropping] = useState(false);
  const [sourceLang, setSourceLang] = useState<SourceLang>(DEFAULT_SOURCE);
  const [languageSet, setLanguageSet] = useState<LanguageSet>({ defaultCode: "zh-TW", languages: [], unavailable: {} });
  const [adding, setAdding] = useState<readonly AddEntry[] | null>(null);
  const [batchRequest, setBatchRequest] = useState(0);
  const { toast, show: showToast, hide: hideToast } = useToast(9000);
  const [firstRun, setFirstRun] = useState<"checking" | "wizard" | "done">("checking");

  useEffect(() => {
    let stop: (() => void) | undefined;
    void watchBackend(setStatus).then((s) => (stop = s));
    return () => stop?.();
  }, []);

  useEffect(() => localStorage.setItem(KEY, JSON.stringify(settings)), [settings]);
  useEffect(() => localStorage.setItem(QUEUE_KEY, JSON.stringify(queue)), [queue]);

  const backend = status.kind === "ready" ? status.backend : null;
  useEffect(() => {
    if (!backend) return;
    let alive = true;
    fetchModelStates(backend).then(
      (models) => alive && setFirstRun(needsWizard(models, localStorage.getItem(SKIPPED_KEY) === "1") ? "wizard" : "done"),
      () => alive && setFirstRun("done"),
    );
    return () => {
      alive = false;
    };
  }, [backend]);
  const leaveWizard = useCallback((how: "finished" | "skipped") => {
    if (how === "skipped") localStorage.setItem(SKIPPED_KEY, "1");
    setFirstRun("done");
  }, []);
  const batch = useBatch(backend);
  useEffect(() => {
    if (backend) performance.mark("backend-ready");
  }, [backend]);

  const load = useCallback(async (b: Backend, projectId: string, lang: string): Promise<Loaded> => {
    const [cues, editedIds] = await Promise.all([fetchCues(b, projectId, lang), fetchEditedIds(b, projectId, lang)]);
    return { cues, editedIds };
  }, []);

  const show = useCallback(
    async (b: Backend, videoPath: string, projectId: string, notice: string | null = null, prefer: string | null = null) => {
      const [project, known, playback] = await Promise.all([
        fetchProject(b, projectId),
        fetchLanguages(b),
        fetchPlayback(b, projectId).catch(() => NO_PLAYBACK),
      ]);
      const languages = project.translatedLangs.flatMap((code) => known.filter((l) => l.code === code));
      const lang = prefer !== null && languages.some((l) => l.code === prefer) ? prefer : languages.some((l) => l.code === project.activeLang) ? project.activeLang : (languages[0]?.code ?? project.activeLang);
      setScreen({ kind: "playing", videoPath, projectId, sourceLang: project.sourceLang, languages, lang, loaded: await load(b, projectId, lang), playback, notice });
      setQueue((q) => playing(q, projectId));
    },
    [load],
  );

  const showLang = useCallback(
    async (code: string) => {
      if (!backend || screen.kind !== "playing") return;
      try {
        const loaded = await load(backend, screen.projectId, code);
        setScreen({ ...screen, lang: code, loaded, notice: null });
      } catch (e) {
        setScreen({ ...screen, notice: `無法切換語言：${message(e)}` });
      }
    },
    [backend, screen, load],
  );

  const startImport = useCallback(
    async (videoPath: string, prefer: string | null = null, chosen: SourceLang | null = null) => {
      if (!backend) return;
      try {
        await allowVideo(videoPath);
        const project = await createProject(backend, videoPath);
        if (project.translated && project.activeJob === null) {
          const differs = chosen !== null && chosen !== project.sourceLang;
          const notice = differs ? `這部影片先前以${sourceLabel(project.sourceLang)}處理，已直接播放` : null;
          await show(backend, videoPath, project.id, notice, prefer);
          return;
        }
        const jobId = project.activeJob ?? (await startJob(backend, project.id, chosen ?? project.sourceLang));
        setScreen({ kind: "importing", videoPath, projectId: project.id, jobId });
      } catch (e) {
        setScreen({ kind: "idle", error: e instanceof ApiError ? e.message : message(e) });
      }
    },
    [backend, show],
  );

  const screenKind = screen.kind;
  const playingId = screen.kind === "playing" ? screen.projectId : null;
  useEffect(() => {
    if (!backend || screenKind === "importing") return;
    let alive = true;
    void Promise.all([fetchLibrary(backend), fetchLanguageSet(backend)]).then(
      ([items, set]) => {
        if (!alive) return;
        setLibrary(items);
        setLanguageSet(set);
        setLanguageNames(new Map(set.languages.map((l) => [l.code, shortName(l.nativeName)])));
        setQueue((q) => pruned(q, new Set(items.map((i) => i.id))));
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [backend, screenKind, playingId]);

  useEffect(() => {
    if (!backend) return;
    let stop: (() => void) | undefined;
    void watchDrops(
      (paths) => {
        const [first] = paths;
        if (first && paths.length === 1 && classifyPath(first) === "file") void startImport(first, null, sourceLang);
        else if (paths.length > 0) setAdding(rowsFor(paths, languageSet.defaultCode, sourceLang));
      },
      setDropping,
    ).then((s) => (stop = s));
    return () => stop?.();
  }, [backend, startImport, languageSet.defaultCode, sourceLang]);

  const playItem = useCallback((item: LibraryItem) => void startImport(item.videoPath), [startImport]);
  const stepVideo = useCallback(
    (dir: 1 | -1) => {
      const id = neighbour(queue, dir);
      const item = library.find((i) => i.id === id);
      if (item) playItem(item);
    },
    [queue, library, playItem],
  );
  const patchSettings = useCallback((patch: Partial<typeof settings>) => setSettings((s) => ({ ...s, ...patch })), []);
  const libraryView = backend && (
    <Library
      backend={backend}
      items={library}
      queue={queue}
      currentId={playingId}
      names={languageNames}
      onPlay={playItem}
      onEnqueue={(id) => setQueue((q) => enqueue(q, id))}
      onDequeue={(id) => setQueue((q) => dequeue(q, id))}
      onQueueAll={() => setQueue((q) => library.reduce((acc, i) => enqueue(acc, i.id), q))}
    />
  );

  const total = overall(batch.items);
  const badge = batch.items.length > 0 ? `${total.finished}/${total.total}` : null;
  const openItem = useCallback((item: BatchItem) => void startImport(item.videoPath, item.lang), [startImport]);
  const showQueue = useCallback(() => {
    if (screen.kind === "playing") setBatchRequest((n) => n + 1);
    else setScreen({ kind: "idle" });
    window.setTimeout(() => document.querySelector('[data-testid="batch-panel"]')?.scrollIntoView({ block: "nearest" }), 50);
  }, [screen.kind]);
  const batchView = backend && (
    <BatchPanel
      backend={backend}
      batch={batch}
      languages={languageSet.languages}
      onOpen={openItem}
      onAdd={() => setAdding([])}
      onError={(text) => showToast({ text, error: true })}
    />
  );

  const finishedN = batch.finished?.n ?? 0;
  const seenFinished = useRef(finishedN);
  useEffect(() => {
    if (finishedN === seenFinished.current) return;
    seenFinished.current = finishedN;
    const c = batch.finished?.counts;
    if (!c) return;
    const text = `佇列已全部處理完：${c.done} 項完成${c.failed > 0 ? `，${c.failed} 項失敗` : ""}${c.cancelled > 0 ? `，${c.cancelled} 項取消` : ""}`;
    showToast({ text, action: { label: "查看佇列", run: showQueue } });
    void notifyWindows("字幕翻譯：佇列完成", text);
  }, [finishedN, batch.finished, showToast, showQueue]);

  const importing = screen.kind === "importing" ? screen : null;
  const finishImport = useCallback(
    (edits: EditsReport) => {
      if (backend && importing) {
        show(backend, importing.videoPath, importing.projectId, editsNotice(edits)).catch((e: unknown) =>
          setScreen({ kind: "idle", error: message(e) }),
        );
      }
    },
    [backend, importing, show],
  );
  const stopImport = useCallback((error?: string) => setScreen({ kind: "idle", ...(error ? { error } : {}) }), []);

  if (backend && firstRun === "wizard") {
    return (
      <div className="app wizard-app">
        <main>
          <Wizard backend={backend} onExit={leaveWizard} />
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="app-top">
        <header>
          {backend && (
            <div className="tool-icons">
              {screen.kind !== "idle" && (
                <button
                  type="button"
                  className="ghost icon-only"
                  data-testid="home"
                  title="回到媒體庫"
                  aria-label="媒體庫"
                  onClick={() => setScreen({ kind: "idle" })}
                  disabled={screen.kind === "importing"}
                >
                  <Home className="icon" aria-hidden />
                </button>
              )}
              <button
                type="button"
                className="icon-only"
                title="批次加入：一次加入多個影片或資料夾"
                aria-label="批次加入"
                data-testid="batch-open-add"
                onClick={() => setAdding([])}
              >
                <ListPlus className="icon" aria-hidden />
              </button>
              {badge && (
                <button
                  type="button"
                  className="icon-only queue-chip"
                  data-testid="queue-chip"
                  data-active={total.active}
                  title={total.etaS !== null ? `佇列 ${badge}：剩餘${formatEta(total.etaS)}` : `佇列 ${badge}`}
                  aria-label={`佇列 ${badge}`}
                  onClick={showQueue}
                >
                  <Layers className="icon" aria-hidden />
                  <span className="chip-badge">{badge}</span>
                  {total.active && (
                    <span className="chip-percent" style={{ width: `${Math.round(total.fraction * 100)}%` }} />
                  )}
                </button>
              )}
              <button
                type="button"
                className="ghost icon-only"
                data-testid="settings-open"
                title="設定：模型、硬體、LLM 來源、授權"
                aria-label="設定"
                aria-pressed={screen.kind === "settings"}
                disabled={screen.kind === "importing"}
                onClick={() => setScreen(screen.kind === "settings" ? { kind: "idle" } : { kind: "settings" })}
              >
                <Settings className="icon" aria-hidden />
              </button>
            </div>
          )}
          <ImportPanel
            busy={!backend || screen.kind === "importing"}
            sourceLang={sourceLang}
            unavailable={languageSet.unavailable}
            onSourceLang={setSourceLang}
            withPicker={screen.kind !== "playing"}
            onImport={(p) => void startImport(p, null, sourceLang)}
          />
          {screen.kind === "playing" && (
            <SettingsBar langName={shortName(playingName(screen))} settings={settings} onChange={setSettings} />
          )}
        </header>
        {SOURCE_NOTES[sourceLang] && (
          <div className="source-bar">
            {screen.kind === "playing" && <SourcePick busy={!backend} sourceLang={sourceLang} unavailable={languageSet.unavailable} onSourceLang={setSourceLang} />}
            <p className="source-note" data-testid="source-note">
              {SOURCE_NOTES[sourceLang]}
            </p>
          </div>
        )}
      </div>
      <main>
        {status.kind === "starting" && (
          <div className="empty" data-testid="starting">
            <LoaderCircle className="spin" aria-hidden />
            <p>正在啟動後端…</p>
          </div>
        )}
        {status.kind === "failed" && (
          <pre className="error" role="alert" data-testid="backend-failed">
            {status.message}
          </pre>
        )}
        {backend && firstRun === "checking" && (
          <div className="empty" data-testid="checking">
            <LoaderCircle className="spin" aria-hidden />
            <p>正在檢查模型…</p>
          </div>
        )}
        {backend && screen.kind === "settings" && <SettingsPage backend={backend} />}
        {screen.kind === "idle" && !screen.error && backend && firstRun === "done" && (
          <div className="home">
            <div className="empty" data-testid="ready">
              <span className="empty-mark">
                <Captions aria-hidden />
              </span>
              <h1>匯入一部演講影片</h1>
              <p>貼上影片路徑、按「選擇檔案」，或把檔案拖到視窗上，再按「匯入」。</p>
              <span className="status-pill">
                <span className="dot" />
                後端已就緒
              </span>
            </div>
            <div className="home-batch">{batchView}</div>
            {library.length > 0 && <div className="home-library">{libraryView}</div>}
          </div>
        )}
        {screen.kind === "idle" && screen.error && (
          <p className="error" role="alert" data-testid="error">
            <TriangleAlert className="icon" aria-hidden />
            <span>
              <LinkedText text={screen.error} />
            </span>
          </p>
        )}
        {backend && importing && (
          <Importing backend={backend} screen={importing} onDone={finishImport} onStop={stopImport} />
        )}
        {backend && screen.kind === "playing" && (
          <Player
            backend={backend}
            projectId={screen.projectId}
            videoPath={screen.videoPath}
            sourceLang={screen.sourceLang}
            settings={settings}
            languages={screen.languages}
            lang={screen.lang}
            onLang={(code) => void showLang(code)}
            loaded={screen.loaded}
            notice={screen.notice}
            playback={screen.playback}
            hasPrevVideo={neighbour(queue, -1) !== null}
            hasNextVideo={neighbour(queue, 1) !== null}
            onStep={stepVideo}
            onSettings={patchSettings}
            library={libraryView}
            batch={batchView}
            batchBadge={badge}
            batchRequest={batchRequest}
          />
        )}
      </main>
      {adding && backend && (
        <AddDialog
          backend={backend}
          languages={languageSet}
          initial={adding}
          onClose={() => setAdding(null)}
          onAdded={(n) => n > 0 && showToast({ text: `已加入 ${n} 項到佇列`, action: { label: "查看佇列", run: showQueue } })}
        />
      )}
      {batch.countdown && backend && <CountdownModal countdown={batch.countdown} onCancel={() => void cancelPower(backend)} />}
      <div className="app-toast">
        <Toast toast={toast} onClose={hideToast} />
      </div>
      {dropping && (
        <div className="drop-hint" data-testid="drop-hint">
          放開滑鼠，匯入這個檔案
        </div>
      )}
    </div>
  );
}
