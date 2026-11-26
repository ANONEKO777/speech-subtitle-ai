import { Captions, Film, Home, Layers, ListPlus, LoaderCircle, Settings, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { isDetection, preselect } from "./api/detect";
import { planImport } from "./api/importPlan";
import { DEFAULT_SOURCE, type SourceLang, sourceLabel, usableSource } from "./api/sourceLang";
import { isExperimentalTarget, targetFor, targetLanguage, targetsOf } from "./api/targets";
import { type BackendStatus, allowVideo, watchBackend } from "./api/backend";
import {
  ApiError,
  type Backend,
  type CueFailures,
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
import { useT } from "./i18n/I18nProvider";
import { languageName } from "./i18n/languageName";
import type { Locale } from "./i18n/locale";
import { ImportPanel } from "./import/ImportPanel";
import { SourceBar } from "./import/SourceBar";
import { useDetections, useSettledPath } from "./import/useDetections";
import { useDrops } from "./import/useDrops";
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
import { useUiLanguageSync } from "./settings/useUiLanguageSync";
import { SettingsBar } from "./settings/SettingsBar";
import { SKIPPED_KEY, needsWizard } from "./wizard/firstRun";
import { Wizard } from "./wizard/Wizard";
import { LinkedText } from "./manage/LinkedText";
import { KEY, parseSettings } from "./settings/settings";

type Screen =
  | { readonly kind: "idle"; readonly error?: string }
  | { readonly kind: "settings" }
  | {
      readonly kind: "importing";
      readonly videoPath: string;
      readonly projectId: string;
      readonly jobId: string;
      /** The language the run translates into, or null for the one the project already had. */
      readonly target: string | null;
      /** The project already has its speech steps, so the run only translates again. */
      readonly addsTarget: boolean;
    }
  | {
      readonly kind: "playing";
      readonly videoPath: string;
      readonly projectId: string;
      readonly sourceLang: SourceLang;
      /** The languages the project has a finished translation for. */
      readonly languages: readonly LanguageInfo[];
      readonly lang: string;
      /** The cues each language's translation could not do. */
      readonly failedCues: Readonly<Record<string, CueFailures>>;
      readonly loaded: Loaded;
      readonly playback: Playback;
      readonly notice: string | null;
    };

const editsNotice = ({ kept, unmatched }: EditsReport, { t, plural }: Pick<ReturnType<typeof useT>, "t" | "plural">): string | null => {
  const parts = [kept > 0 ? plural("edits.kept", kept) : "", unmatched > 0 ? plural("edits.unmatched", unmatched) : ""].filter(Boolean);
  return parts.length > 0 ? parts.join(t("edits.join")) : null;
};

const playingName = (screen: Extract<Screen, { kind: "playing" }>, locale: Locale) =>
  languageName(locale, screen.languages.find((l) => l.code === screen.lang) ?? { code: screen.lang });

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const fileName = (path: string) => path.slice(Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) + 1);

function Importing({
  backend,
  screen,
  targetLabel,
  onDone,
  onStop,
}: {
  backend: Backend;
  screen: Extract<Screen, { kind: "importing" }>;
  /** The name of the language the run translates into. */
  targetLabel: string;
  onDone: (edits: EditsReport) => void;
  onStop: (error?: string) => void;
}) {
  const { t } = useT();
  const view = useJob(backend, screen.jobId);
  useEffect(() => {
    if (view.kind === "done") onDone(view.edits);
    if (view.kind === "failed") onStop(t("app.processingFailed", { reason: view.disconnected ? t("errors.backendLost") : view.error }));
    if (view.kind === "cancelled") onStop();
  }, [view, onDone, onStop, t]);
  return (
    <section className="importing" data-testid="importing">
      <div className="card importing-card">
        <div className="importing-head">
          <span className="badge-icon">
            <Film aria-hidden />
          </span>
          <div className="importing-title">
            <span className="eyebrow">{t("app.processing")}</span>
            <h2>{fileName(screen.videoPath)}</h2>
            <span className="path">{screen.videoPath}</span>
          </div>
        </div>
        <ProgressBar view={view} target={targetLabel} addsTarget={screen.addsTarget} />
        <button type="button" className="ghost" onClick={() => void cancelJob(backend, screen.jobId)}>
          <X className="icon" aria-hidden />
          {t("common.cancel")}
        </button>
      </div>
    </section>
  );
}

export function App() {
  const texts = useT();
  const { t, plural, locale } = texts;
  const [status, setStatus] = useState<BackendStatus>({ kind: "starting" });
  const [screen, setScreen] = useState<Screen>({ kind: "idle" });
  const [settings, setSettings] = useState(() => parseSettings(localStorage.getItem(KEY)));
  const [queue, setQueue] = useState(() => parseQueue(localStorage.getItem(QUEUE_KEY)));
  const [library, setLibrary] = useState<readonly LibraryItem[]>([]);
  const [languageNames, setLanguageNames] = useState<ReadonlyMap<string, string>>(new Map());
  const [dropping, setDropping] = useState(false);
  const [sourceLang, setSourceLang] = useState<SourceLang>(DEFAULT_SOURCE);
  const [wantedTarget, setWantedTarget] = useState("zh-TW");
  const [typedPath, setTypedPath] = useState("");
  const pickedByHand = useRef(false);
  const preselectedFor = useRef("");
  const [languageSet, setLanguageSet] = useState<LanguageSet>({ defaultCode: "zh-TW", languages: [], unavailable: {}, targets: {} });
  const target = targetFor(languageSet, sourceLang, wantedTarget);
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
  useUiLanguageSync(backend);
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
      setScreen({
        kind: "playing",
        videoPath,
        projectId,
        sourceLang: project.sourceLang,
        languages,
        lang,
        failedCues: project.failedCues,
        loaded: await load(b, projectId, lang),
        playback,
        notice,
      });
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
        setScreen({ ...screen, notice: t("app.switchLanguageFailed", { reason: message(e) }) });
      }
    },
    [backend, screen, load, t],
  );

  const startImport = useCallback(
    async (videoPath: string, prefer: string | null = null, chosen: SourceLang | null = null, wanted: string | null = null) => {
      if (!backend) return;
      pickedByHand.current = false;
      try {
        await allowVideo(videoPath);
        const project = await createProject(backend, videoPath);
        const plan = planImport(project, chosen, wanted, languageSet);
        if (plan.kind === "play") {
          const differs = chosen !== null && chosen !== project.sourceLang;
          const notice = differs ? t("app.playedDirectly", { source: sourceLabel(project.sourceLang, t) }) : null;
          await show(backend, videoPath, project.id, notice, prefer ?? plan.prefer);
          return;
        }
        const jobId = project.activeJob ?? (await startJob(backend, project.id, plan.source, plan.target, t));
        setScreen({ kind: "importing", videoPath, projectId: project.id, jobId, target: plan.target, addsTarget: plan.addsTarget });
      } catch (e) {
        setScreen({ kind: "idle", error: e instanceof ApiError ? e.message : message(e) });
      }
    },
    [backend, show, languageSet, t],
  );

  const addTarget = useCallback(
    async (code: string) => {
      if (!backend || screen.kind !== "playing") return;
      try {
        const jobId = await startJob(backend, screen.projectId, screen.sourceLang, code, t);
        setScreen({ kind: "importing", videoPath: screen.videoPath, projectId: screen.projectId, jobId, target: code, addsTarget: true });
      } catch (e) {
        setScreen({ ...screen, notice: t("app.addTargetFailed", { reason: e instanceof ApiError ? e.message : message(e) }) });
      }
    },
    [backend, screen, t],
  );

  const chooseSource = useCallback((code: SourceLang) => {
    pickedByHand.current = true;
    setSourceLang(code);
  }, []);
  const importPath = useSettledPath(typedPath, screen.kind === "idle" || screen.kind === "settings");
  const detections = useDetections(backend, importPath === "" ? [] : [importPath]);
  const found = importPath === "" ? undefined : detections.get(importPath);
  useEffect(() => {
    if (!isDetection(found) || preselectedFor.current === importPath) return;
    preselectedFor.current = importPath;
    const code = preselect(found, pickedByHand.current, languageSet.unavailable);
    if (code !== null) setSourceLang(code);
  }, [found, importPath, languageSet.unavailable]);

  const screenKind = screen.kind;
  const playingId = screen.kind === "playing" ? screen.projectId : null;
  useEffect(() => {
    if (!backend || screenKind === "importing") return;
    let alive = true;
    void Promise.all([fetchLibrary(backend), fetchLanguageSet(backend, t)]).then(
      ([items, set]) => {
        if (!alive) return;
        setLibrary(items);
        setLanguageSet(set);
        setSourceLang((picked) => usableSource(picked, set.unavailable));
        setLanguageNames(new Map(set.languages.map((l) => [l.code, languageName(locale, l)])));
        setQueue((q) => pruned(q, new Set(items.map((i) => i.id))));
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [backend, screenKind, playingId, t, locale]);

  useDrops(
    backend !== null,
    (paths) => {
      const [first] = paths;
      if (first && paths.length === 1 && classifyPath(first) === "file") void startImport(first, null, sourceLang, target);
      else if (paths.length > 0) setAdding(rowsFor(paths, [target], sourceLang));
    },
    setDropping,
  );

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

  const experimentalPick = screen.kind !== "playing" && isExperimentalTarget(languageSet, sourceLang, target);
  const playingScreen = screen.kind === "playing" ? screen : null;
  const addBlocked =
    playingScreen && batch.items.some((i) => i.projectId === playingScreen.projectId && i.state === "running")
      ? t("app.addTargetBlocked")
      : null;
  const experimental = new Set(
    playingScreen?.languages.filter((l) => isExperimentalTarget(languageSet, playingScreen.sourceLang, l.code)).map((l) => l.code),
  );
  const addable = playingScreen
    ? targetsOf(languageSet, playingScreen.sourceLang).filter((t) => !playingScreen.languages.some((l) => l.code === t.code))
    : [];
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
    const text = [
      t("queue.finished", { done: c.done }),
      c.failed > 0 ? t("queue.finishedFailed", { n: c.failed }) : "",
      c.cancelled > 0 ? t("queue.finishedCancelled", { n: c.cancelled }) : "",
    ].join("");
    showToast({ text, action: { label: t("queue.view"), run: showQueue } });
    void notifyWindows(t("queue.notifyTitle"), text);
  }, [finishedN, batch.finished, showToast, showQueue, t]);

  const importing = screen.kind === "importing" ? screen : null;
  const finishImport = useCallback(
    (edits: EditsReport) => {
      if (backend && importing) {
        show(backend, importing.videoPath, importing.projectId, editsNotice(edits, texts), importing.target).catch((e: unknown) =>
          setScreen({ kind: "idle", error: message(e) }),
        );
      }
    },
    [backend, importing, show, texts],
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
                  title={t("app.libraryTitle")}
                  aria-label={t("app.library")}
                  onClick={() => setScreen({ kind: "idle" })}
                  disabled={screen.kind === "importing"}
                >
                  <Home className="icon" aria-hidden />
                </button>
              )}
              <button
                type="button"
                className="icon-only"
                title={t("app.batchTitle")}
                aria-label={t("app.batch")}
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
                  title={total.etaS !== null ? t("app.queueEta", { badge, eta: formatEta(total.etaS, t) }) : t("app.queue", { badge })}
                  aria-label={t("app.queue", { badge })}
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
                title={t("app.settingsTitle")}
                aria-label={t("app.settings")}
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
            onSourceLang={chooseSource}
            targets={targetsOf(languageSet, sourceLang)}
            target={target}
            onTarget={setWantedTarget}
            withPicker={screen.kind !== "playing"}
            onImport={(p) => void startImport(p, null, sourceLang, target)}
            onPath={setTypedPath}
          />
          {screen.kind === "playing" && (
            <SettingsBar langName={playingName(screen, locale)} settings={settings} onChange={setSettings} />
          )}
        </header>
        <SourceBar
          playing={screen.kind === "playing"}
          busy={!backend}
          sourceLang={sourceLang}
          unavailable={languageSet.unavailable}
          onSourceLang={chooseSource}
          found={found}
          experimentalPick={experimentalPick}
        />
      </div>
      <main>
        {status.kind === "starting" && (
          <div className="empty" data-testid="starting">
            <LoaderCircle className="spin" aria-hidden />
            <p>{t("app.starting")}</p>
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
            <p>{t("app.checkingModels")}</p>
          </div>
        )}
        {backend && screen.kind === "settings" && <SettingsPage backend={backend} />}
        {screen.kind === "idle" && !screen.error && backend && firstRun === "done" && (
          <div className="home">
            <div className="empty" data-testid="ready">
              <span className="empty-mark">
                <Captions aria-hidden />
              </span>
              <h1>{t("app.importHeading")}</h1>
              <p>{t("app.importHint")}</p>
              <span className="status-pill">
                <span className="dot" />
                {t("app.ready")}
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
          <Importing
            backend={backend}
            screen={importing}
            targetLabel={languageName(locale, targetLanguage(languageSet, sourceLang, importing.target ?? languageSet.defaultCode))}
            onDone={finishImport}
            onStop={stopImport}
          />
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
            experimental={experimental}
            addable={addable}
            onAddTarget={(code) => void addTarget(code)}
            addBlocked={addBlocked}
            failures={screen.failedCues[screen.lang]}
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
          onAdded={(n) => n > 0 && showToast({ text: plural("queue.added", n), action: { label: t("queue.view"), run: showQueue } })}
        />
      )}
      {batch.countdown && backend && <CountdownModal countdown={batch.countdown} onCancel={() => void cancelPower(backend)} />}
      <div className="app-toast">
        <Toast toast={toast} onClose={hideToast} />
      </div>
      {dropping && (
        <div className="drop-hint" data-testid="drop-hint">
          {t("app.dropHint")}
        </div>
      )}
    </div>
  );
}
