import { Captions, Film, Home, LoaderCircle, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type BackendStatus, allowVideo, watchBackend, watchDrops } from "./api/backend";
import {
  ApiError,
  type Backend,
  type LanguageInfo,
  cancelJob,
  createProject,
  fetchCues,
  fetchEditedIds,
  fetchLanguages,
  fetchProject,
  startJob,
} from "./api/client";
import { type LibraryItem, NO_PLAYBACK, type Playback, fetchLibrary, fetchPlayback } from "./api/library";
import type { Loaded } from "./editor/useCueEditing";
import { shortName } from "./export/exports";
import { ImportPanel } from "./import/ImportPanel";
import { Library } from "./player/Library";
import { Player } from "./player/Player";
import { QUEUE_KEY, dequeue, enqueue, neighbour, parseQueue, playing, pruned } from "./player/queue";
import { ProgressBar } from "./progress/ProgressBar";
import type { EditsReport } from "./progress/job";
import { useJob } from "./progress/useJob";
import { SettingsBar } from "./settings/SettingsBar";
import { KEY, parseSettings } from "./settings/settings";

type Screen =
  | { readonly kind: "idle"; readonly error?: string }
  | { readonly kind: "importing"; readonly videoPath: string; readonly projectId: string; readonly jobId: string }
  | {
      readonly kind: "playing";
      readonly videoPath: string;
      readonly projectId: string;
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
    unmatched > 0 ? `${unmatched} 條修改因英文原文已變而沒有套用，仍存在專案資料夾的 edits 檔` : "",
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

  useEffect(() => {
    let stop: (() => void) | undefined;
    void watchBackend(setStatus).then((s) => (stop = s));
    return () => stop?.();
  }, []);

  useEffect(() => localStorage.setItem(KEY, JSON.stringify(settings)), [settings]);
  useEffect(() => localStorage.setItem(QUEUE_KEY, JSON.stringify(queue)), [queue]);

  const backend = status.kind === "ready" ? status.backend : null;
  useEffect(() => {
    if (backend) performance.mark("backend-ready");
  }, [backend]);

  const load = useCallback(async (b: Backend, projectId: string, lang: string): Promise<Loaded> => {
    const [cues, editedIds] = await Promise.all([fetchCues(b, projectId, lang), fetchEditedIds(b, projectId, lang)]);
    return { cues, editedIds };
  }, []);

  const show = useCallback(
    async (b: Backend, videoPath: string, projectId: string, notice: string | null = null) => {
      const [project, known, playback] = await Promise.all([
        fetchProject(b, projectId),
        fetchLanguages(b),
        fetchPlayback(b, projectId).catch(() => NO_PLAYBACK),
      ]);
      const languages = project.translatedLangs.flatMap((code) => known.filter((l) => l.code === code));
      const lang = languages.some((l) => l.code === project.activeLang) ? project.activeLang : (languages[0]?.code ?? project.activeLang);
      setScreen({ kind: "playing", videoPath, projectId, languages, lang, loaded: await load(b, projectId, lang), playback, notice });
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
    async (videoPath: string) => {
      if (!backend) return;
      try {
        await allowVideo(videoPath);
        const project = await createProject(backend, videoPath);
        if (project.translated && project.activeJob === null) {
          await show(backend, videoPath, project.id);
          return;
        }
        const jobId = project.activeJob ?? (await startJob(backend, project.id));
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
    void Promise.all([fetchLibrary(backend), fetchLanguages(backend)]).then(
      ([items, known]) => {
        if (!alive) return;
        setLibrary(items);
        setLanguageNames(new Map(known.map((l) => [l.code, shortName(l.nativeName)])));
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
        const path = paths[0];
        if (path) void startImport(path);
      },
      setDropping,
    ).then((s) => (stop = s));
    return () => stop?.();
  }, [backend, startImport]);

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

  return (
    <div className="app">
      <header>
        {screen.kind !== "idle" && (
          <div className="tool-icons">
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
          </div>
        )}
        <ImportPanel busy={!backend || screen.kind === "importing"} onImport={(p) => void startImport(p)} />
        {screen.kind === "playing" && (
          <SettingsBar langName={shortName(playingName(screen))} settings={settings} onChange={setSettings} />
        )}
      </header>
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
        {screen.kind === "idle" && !screen.error && backend && (
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
            {library.length > 0 && <div className="home-library">{libraryView}</div>}
          </div>
        )}
        {screen.kind === "idle" && screen.error && (
          <p className="error" role="alert" data-testid="error">
            <TriangleAlert className="icon" aria-hidden />
            <span>{screen.error}</span>
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
          />
        )}
      </main>
      {dropping && (
        <div className="drop-hint" data-testid="drop-hint">
          放開滑鼠，匯入這個檔案
        </div>
      )}
    </div>
  );
}
