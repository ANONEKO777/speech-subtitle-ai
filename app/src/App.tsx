import { Captions, Film, LoaderCircle, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type BackendStatus, allowVideo, watchBackend } from "./api/backend";
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
import type { Loaded } from "./editor/useCueEditing";
import { shortName } from "./export/exports";
import { ImportPanel } from "./import/ImportPanel";
import { Player } from "./player/Player";
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

  useEffect(() => {
    let stop: (() => void) | undefined;
    void watchBackend(setStatus).then((s) => (stop = s));
    return () => stop?.();
  }, []);

  useEffect(() => localStorage.setItem(KEY, JSON.stringify(settings)), [settings]);

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
      const [project, known] = await Promise.all([fetchProject(b, projectId), fetchLanguages(b)]);
      const languages = project.translatedLangs.flatMap((code) => known.filter((l) => l.code === code));
      const lang = languages.some((l) => l.code === project.activeLang) ? project.activeLang : (languages[0]?.code ?? project.activeLang);
      setScreen({ kind: "playing", videoPath, projectId, languages, lang, loaded: await load(b, projectId, lang), notice });
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
          <div className="empty" data-testid="ready">
            <span className="empty-mark">
              <Captions aria-hidden />
            </span>
            <h1>匯入一部演講影片</h1>
            <p>貼上影片路徑或按「選擇檔案」，再按「匯入」。</p>
            <span className="status-pill">
              <span className="dot" />
              後端已就緒
            </span>
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
          />
        )}
      </main>
    </div>
  );
}
