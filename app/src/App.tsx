import { useCallback, useEffect, useState } from "react";
import { type BackendStatus, allowVideo, watchBackend } from "./api/backend";
import { ApiError, type Backend, cancelJob, createProject, fetchCues, startJob } from "./api/client";
import { ImportPanel } from "./import/ImportPanel";
import type { Cue } from "./player/cues";
import { Player } from "./player/Player";
import { ProgressBar } from "./progress/ProgressBar";
import { useJob } from "./progress/useJob";
import { SettingsBar } from "./settings/SettingsBar";
import { KEY, parseSettings } from "./settings/settings";

type Screen =
  | { readonly kind: "idle"; readonly error?: string }
  | { readonly kind: "importing"; readonly videoPath: string; readonly projectId: string; readonly jobId: string }
  | { readonly kind: "playing"; readonly videoPath: string; readonly cues: readonly Cue[] };

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Importing({
  backend,
  screen,
  onDone,
  onStop,
}: {
  backend: Backend;
  screen: Extract<Screen, { kind: "importing" }>;
  onDone: () => void;
  onStop: (error?: string) => void;
}) {
  const view = useJob(backend, screen.jobId);
  useEffect(() => {
    if (view.kind === "done") onDone();
    if (view.kind === "failed") onStop(`處理失敗：${view.error}`);
    if (view.kind === "cancelled") onStop();
  }, [view, onDone, onStop]);
  return (
    <section className="importing" data-testid="importing">
      <h2>正在處理 {screen.videoPath}</h2>
      <ProgressBar view={view} />
      <button type="button" onClick={() => void cancelJob(backend, screen.jobId)}>
        取消
      </button>
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

  const show = useCallback(
    async (b: Backend, videoPath: string, projectId: string) => {
      setScreen({ kind: "playing", videoPath, cues: await fetchCues(b, projectId) });
    },
    [],
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
  const finishImport = useCallback(() => {
    if (backend && importing) {
      show(backend, importing.videoPath, importing.projectId).catch((e: unknown) =>
        setScreen({ kind: "idle", error: message(e) }),
      );
    }
  }, [backend, importing, show]);
  const stopImport = useCallback((error?: string) => setScreen({ kind: "idle", ...(error ? { error } : {}) }), []);

  return (
    <div className="app">
      <header>
        <ImportPanel busy={!backend || screen.kind === "importing"} onImport={(p) => void startImport(p)} />
        {screen.kind === "playing" && <SettingsBar settings={settings} onChange={setSettings} />}
      </header>
      <main>
        {status.kind === "starting" && <p className="hint" data-testid="starting">正在啟動後端…</p>}
        {status.kind === "failed" && (
          <pre className="error" role="alert" data-testid="backend-failed">
            {status.message}
          </pre>
        )}
        {screen.kind === "idle" && !screen.error && backend && (
          <p className="hint" data-testid="ready">
            後端已就緒。貼上影片路徑或按「選擇檔案」，再按「匯入」。
          </p>
        )}
        {screen.kind === "idle" && screen.error && (
          <p className="error" role="alert" data-testid="error">
            {screen.error}
          </p>
        )}
        {backend && importing && (
          <Importing backend={backend} screen={importing} onDone={finishImport} onStop={stopImport} />
        )}
        {screen.kind === "playing" && <Player videoPath={screen.videoPath} cues={screen.cues} settings={settings} />}
      </main>
    </div>
  );
}
