// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { parseUnavailable } from "../api/sourceLang";
import { detectLine } from "../api/detect";
import type { Detected } from "../api/detect";
import { EMPTY_BATCH, type Batch, type BatchItem } from "../batch/model";
import { ImportPanel } from "../import/ImportPanel";
import { SourceBar } from "../import/SourceBar";
import { ProgressBar } from "../progress/ProgressBar";
import { WAITING, reduceJob, type JobView } from "../progress/job";
import { HardwareSection } from "../settings/HardwareSection";
import { LicensesSection } from "../settings/LicensesSection";
import { LlmSection } from "../settings/LlmSection";
import { SettingsBar } from "../settings/SettingsBar";
import { SettingsPage } from "../settings/SettingsPage";
import { UpdateSection } from "../settings/UpdateSection";
import { DEFAULTS } from "../settings/settings";
import { licenses, macView, windowsView } from "../manage/screens.fixture";
import type { DownloadJob, LlmTest, ProfileView, SelfTest, SettingsView } from "../manage/types";
import { I18nProvider } from "./I18nProvider";
import { type Translate, t } from ".";
import type { Locale } from "./locale";
import { NOT_ENGLISH } from "./notEnglish";
import { plainText, type Said } from "./said";

/**
 * Every W1 screen rendered in each released language. Traditional Chinese must equal what the screens
 * said before the catalog (`w1.screens.zh-TW.fixture.json`, written from `main` with W1_FIXTURE=write),
 * and English must hold no Chinese or Japanese characters. The stubs hold Latin text only, so any
 * CJK character on the English render is text the catalog did not carry.
 */

const mocks = vi.hoisted(() => ({
  status: { kind: "ready" } as { kind: string; backend?: { port: number; token: string }; error?: Said },
  profile: null as unknown,
  change: null as unknown,
  selfTests: [] as unknown[],
  jobs: [] as unknown[],
  settings: null as unknown,
  test: null as unknown,
  licenses: [] as readonly unknown[],
  check: null as unknown,
  checkMode: "ok" as "ok" | "nonsense" | "unknown",
  download: null as unknown,
  project: null as unknown,
  jobView: null as unknown,
  dropping: false,
  checking: false,
  batch: null as unknown,
}));

const backend = { port: 1, token: "t" };

vi.mock("@tauri-apps/api/core", () => ({ convertFileSrc: (p: string) => p, invoke: () => Promise.resolve(null) }));
vi.mock("../api/backend", () => ({
  watchBackend: (onStatus: (s: unknown) => void) => {
    onStatus(mocks.status.kind === "ready" ? { kind: "ready", backend } : mocks.status);
    return Promise.resolve(() => undefined);
  },
  allowVideo: () => Promise.resolve(),
  watchDrops: () => Promise.resolve(() => undefined),
  openFolder: () => Promise.resolve(),
  pickFolder: () => Promise.resolve(null),
  pickVideo: () => Promise.resolve(null),
  pickVideos: () => Promise.resolve([]),
  saveExport: () => Promise.resolve(null),
}));
vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: () => Promise.resolve(mocks.profile),
  fetchLastSelfTest: () => Promise.resolve(null),
  chooseProfile: () => Promise.resolve(mocks.change),
  runSelfTest: () => Promise.resolve(mocks.selfTests.shift()),
  downloadProfileAssets: () => Promise.resolve(mocks.jobs),
  fetchSettings: () => Promise.resolve(mocks.settings),
  saveLlm: () => Promise.resolve(mocks.settings),
  testLlm: () => Promise.resolve(mocks.test),
  fetchLicenses: () => Promise.resolve(mocks.licenses),
  openUrl: () => Promise.resolve(),
  fetchDownloads: () => Promise.resolve([]),
  fetchModelStates: () => (mocks.checking ? new Promise(() => undefined) : Promise.resolve([])),
  saveUiLanguage: () => Promise.resolve(),
}));
vi.mock("../settings/update", async (orig) => {
  const real = await orig<typeof import("../settings/update")>();
  return {
    ...real,
    updateCheck: (tr?: Translate) => {
      if (mocks.checkMode === "nonsense") return Promise.resolve().then(() => real.parseChecked({ state: "weird" }, tr));
      if (mocks.checkMode === "unknown") return Promise.reject(undefined);
      return mocks.check instanceof Promise ? mocks.check : Promise.resolve(mocks.check);
    },
    updateDownload: () => (mocks.download instanceof Promise ? mocks.download : Promise.resolve()),
    updateInstall: () => new Promise(() => undefined),
  };
});
vi.mock("../batch/useBatch", () => ({ useBatch: () => mocks.batch }));
vi.mock("../batch/notify", () => ({ notifyWindows: () => Promise.resolve() }));
vi.mock("../summary/useSummary", () => ({ useSummary: () => null }));
vi.mock("../progress/useJob", () => ({ useJob: () => mocks.jobView }));
vi.mock("../import/useDrops", async () => {
  const { useEffect } = await import("react");
  return {
    useDrops: (_enabled: boolean, _onDrop: unknown, onOver: (over: boolean) => void) => {
      useEffect(() => {
        if (mocks.dropping) onOver(true);
      }, [onOver]);
    },
  };
});
vi.mock("../player/Player", () => ({
  Player: (p: { notice: string | null; addBlocked: string | null }) => (
    <div data-testid="player-stub">
      <p data-testid="stub-notice">{p.notice}</p>
      <p data-testid="stub-blocked">{p.addBlocked}</p>
    </div>
  ),
}));
vi.mock("../player/Library", () => ({ Library: () => null }));
vi.mock("../batch/BatchPanel", () => ({ BatchPanel: () => null }));
vi.mock("../batch/CountdownModal", () => ({ CountdownModal: () => null }));
vi.mock("../batch/AddDialog", () => ({
  rowsFor: () => [],
  AddDialog: ({ onAdded }: { onAdded: (n: number) => void }) => (
    <button type="button" data-testid="stub-added" onClick={() => onAdded(3)}>
      added
    </button>
  ),
}));

const ATTRS = ["title", "aria-label", "placeholder", "alt", "label"] as const;
interface Harvest {
  readonly text: string;
  readonly attrs: readonly string[];
}

function harvest(root: Element): Harvest {
  const text = (root.textContent ?? "").replace(/\s+/g, " ").trim();
  const attrs: string[] = [];
  for (const node of [root, ...root.querySelectorAll("*")]) {
    for (const name of ATTRS) {
      const value = node.getAttribute(name);
      if (value) attrs.push(`${name}=${value}`);
    }
  }
  return { text, attrs };
}


const FIXTURE = "src/i18n/w1.screens.zh-TW.fixture.json";
const WRITE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["W1_FIXTURE"] === "write";
interface Files {
  readFileSync: (path: string, encoding: string) => string;
  writeFileSync: (path: string, data: string, encoding: string) => void;
}
const files = async () => (await import("node:fs" as string)) as Files;
const written: Record<string, Harvest[]> = {};

const downloads = (list: readonly DownloadJob[] = []) => ({ list, byAsset: new Map(), refresh: () => undefined });
const job: DownloadJob = {
  id: "j1",
  assetId: "whisper-large-v3-turbo",
  state: "downloading",
  bytesDone: 400_000_000,
  bytesTotal: 1_600_000_000,
  speedBps: 5_000_000,
  resumedFrom: 100_000_000,
  retries: 2,
  note: null,
  failure: null,
};

const withActive = (view: ProfileView, id: ProfileView["active"]["id"], missing?: ProfileView["profiles"][number]["missing"]): ProfileView => ({
  ...view,
  active: { ...view.active, id, source: "user" },
  profiles: view.profiles.map((p) => ({ ...p, active: p.id === id, ...(p.id === id && missing ? { missing, downloadBytes: 0 } : {}) })),
});

const run = (over: Partial<SelfTest>): SelfTest => ({ ok: true, device: "cuda", stages: [], fallback: null, seconds: 4.2, message: plainText("ok"), ...over });
const stage = (name: string, ok: boolean) => ({ stage: name, runtimeId: `${name}-rt`, device: "cuda", installed: true, ok, seconds: 1.5, detail: plainText("driver too old") });

const llmView = (over: Partial<SettingsView["llm"]> = {}, problem: string | null = null): SettingsView => ({
  uiLanguage: "zh-TW",
  llm: { source: "builtin", ollamaUrl: "http://127.0.0.1:11434", ollamaModel: "", cloudUrl: "", cloudModel: "", cloudConsent: false, apiKeySet: false, ...over },
  consentText: "",
  problem: problem === null ? null : plainText(problem),
  storage: { userData: "C:/u", modelsDir: "C:/m", runtimesDir: "C:/r", defaultModelsDir: "C:/m", usingDefault: true } as unknown as SettingsView["storage"],
});

const click = (id: string) => fireEvent.click(screen.getByTestId(id));
const typeInto = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });

type Shot = (name: string, root?: Element) => void;
type Screen = (shot: Shot, locale: Locale) => Promise<void>;

const said = (locale: Locale): Translate => ((key: never, ...args: never[]) => (t as (l: Locale, k: never, ...a: never[]) => string)(locale, key, ...args)) as Translate;
const wrap = (locale: Locale, node: ReactNode) => <I18nProvider initial={locale}>{node}</I18nProvider>;

const SCREENS: Record<string, Screen> = {
  "hardware on a PC: switching, downloading and the self-test": async (shot, locale) => {
    mocks.profile = windowsView();
    mocks.change = { profile: withActive(windowsView(), "cpu"), warnings: ["Low disk space"] };
    mocks.jobs = [job];
    mocks.selfTests = [
      run({ stages: [stage("asr", true), stage("llm", false)], fallback: { reason: plainText("CUDA failed to start") } }),
      run({ ok: false, stages: [stage("asr", false)], message: plainText("Nothing started") }),
      run({ stages: [stage("asr", true), stage("llm", true)] }),
    ];
    const list = [job];
    const { container, rerender } = render(wrap(locale, <HardwareSection backend={backend} downloads={downloads()} onOpenLlm={() => undefined} />));
    await screen.findByTestId("hw-gpu");
    shot("pc", container);
    click("profile-use-cpu");
    await screen.findByTestId("switch-result");
    shot("pc switched", container);
    click("switch-download");
    rerender(wrap(locale, <HardwareSection backend={backend} downloads={downloads(list)} onOpenLlm={() => undefined} />));
    await screen.findByTestId("switch-jobs");
    shot("pc downloading", container);
    for (const name of ["fallback", "failed", "passed"]) {
      click("selftest-run");
      await screen.findByTestId("selftest-result");
      shot(`pc self-test ${name}`, container);
    }
  },
  "hardware on a Mac: chip, local build and the processor-only notice": async (shot, locale) => {
    mocks.profile = macView();
    const buildOnly = [{ id: "whispercpp-b5454-macos-metal", type: "runtime", sizeBytes: 0, localBuild: true }];
    mocks.change = { profile: withActive(macView(), "apple-cpu", buildOnly), warnings: [] };
    mocks.jobs = [];
    const { container } = render(wrap(locale, <HardwareSection backend={backend} downloads={downloads()} onOpenLlm={() => undefined} />));
    await screen.findByTestId("hw-gpu");
    shot("mac", container);
    click("profile-use-apple-cpu");
    await screen.findByTestId("switch-result");
    shot("mac switched", container);
  },
  "hardware with a fallback banner": async (shot, locale) => {
    mocks.profile = { ...withActive(windowsView(), "cpu"), fallback: { reason: plainText("CUDA failed to start") } };
    const { container } = render(wrap(locale, <HardwareSection backend={backend} downloads={downloads()} onOpenLlm={() => undefined} />));
    await screen.findByTestId("fallback-banner");
    shot("banner", container);
  },
  "LLM source: Ollama, cloud, the test result and the saved note": async (shot, locale) => {
    mocks.settings = llmView({}, "settings.json is damaged");
    const { container } = render(wrap(locale, <LlmSection backend={backend} />));
    await screen.findByTestId("llm-source-ollama");
    shot("builtin", container);
    click("llm-source-ollama");
    shot("ollama", container);
    click("llm-source-cloud");
    shot("cloud", container);
    typeInto("cloud-url", "http://api.example.com/v1");
    shot("cloud with an http address", container);
    typeInto("cloud-url", "https://api.example.com/v1");
    typeInto("cloud-model", "gpt-x");
    typeInto("cloud-key", "sk-test");
    click("cloud-consent");
    mocks.test = { ok: true, url: "https://api.example.com/v1", detail: plainText("Reached it"), models: ["gpt-x", "gpt-y"] } satisfies LlmTest;
    click("llm-test");
    await screen.findByTestId("llm-test-result");
    shot("tested", container);
    mocks.test = { ok: false, url: "", detail: plainText("Connection refused"), models: [] } satisfies LlmTest;
    click("llm-test");
    await waitFor(() => expect(screen.getByTestId("llm-test-result").getAttribute("data-ok")).toBe("false"));
    shot("test failed", container);
    mocks.settings = llmView({ source: "cloud", cloudUrl: "https://api.example.com/v1", cloudModel: "gpt-x", cloudConsent: true, apiKeySet: true });
    click("llm-save");
    await screen.findByTestId("llm-saved");
    shot("saved", container);
    typeInto("cloud-url", "https://other.example.com/v1");
    shot("url moved", container);
  },
  "licenses": async (shot, locale) => {
    mocks.licenses = licenses;
    const { container } = render(wrap(locale, <LicensesSection backend={backend} />));
    await screen.findByTestId("licenses-table");
    shot("table", container);
  },
  "updates: every phase": async (shot, locale) => {
    const { container } = render(wrap(locale, <UpdateSection />));
    shot("idle", container);
    let finish: (v: unknown) => void = () => undefined;
    mocks.check = new Promise((r) => (finish = r));
    click("update-check");
    shot("checking", container);
    await act(async () => finish({ state: "upToDate", current: "0.1.0" }));
    shot("up to date", container);
    mocks.check = { state: "upToDate", current: "" };
    click("update-check");
    await waitFor(() => expect(screen.getByTestId("update-uptodate").textContent).not.toContain("0.1.0"));
    shot("up to date, no version", container);
    mocks.check = { state: "available", current: "0.1.0", version: "0.2.0", notes: "Faster export" };
    click("update-check");
    await screen.findByTestId("update-available");
    shot("available", container);
    let done: () => void = () => undefined;
    mocks.download = new Promise<void>((r) => (done = r));
    click("update-download");
    shot("downloading", container);
    await act(async () => done());
    await screen.findByTestId("update-downloaded");
    shot("downloaded", container);
    click("update-install");
    shot("installing", container);
  },
  "update checks that fail": async (shot, locale) => {
    for (const mode of ["nonsense", "unknown"] as const) {
      mocks.checkMode = mode;
      const { container, unmount } = render(wrap(locale, <UpdateSection />));
      click("update-check");
      await screen.findByTestId("update-failed");
      shot(mode, container);
      unmount();
    }
  },
  "the settings page frame": async (shot, locale) => {
    mocks.licenses = [];
    mocks.settings = llmView();
    const { container } = render(wrap(locale, <SettingsPage backend={backend} initial="update" />));
    shot("update", container);
    click("section-language");
    const names = container.cloneNode(true) as Element;
    for (const option of names.querySelectorAll("#ui-language option")) option.remove();
    shot("language", names);
    click("section-llm");
    await screen.findByTestId("llm-section");
    shot("llm", container);
  },
  "the subtitle bar of the player": async (shot, locale) => {
    const { container } = render(wrap(locale, <SettingsBar langName="Chinese" settings={DEFAULTS} onChange={() => undefined} />));
    shot("bar", container);
  },
  "the import header": async (shot, locale) => {
    const sources = [
      { code: "ja+en", available: false, reason: "cpu" },
      { code: "ja", available: true, reason: null },
    ];
    const targets = [
      { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", experimental: false },
      { code: "ko", name: "Korean", nativeName: "한국어", experimental: true },
    ];
    const unavailable = parseUnavailable(sources, said(locale));
    const props = { busy: false, sourceLang: "ja" as const, unavailable, onSourceLang: () => undefined, targets, target: "ko", onTarget: () => undefined, onImport: () => undefined, onPath: () => undefined };
    const first = render(wrap(locale, <ImportPanel {...props} withPicker />));
    shot("with a picker", first.container);
    first.unmount();
    const second = render(wrap(locale, <ImportPanel {...props} targets={[targets[0]!]} target="zh-TW" withPicker />));
    shot("one target", second.container);
    second.unmount();
    const third = render(wrap(locale, <ImportPanel {...props} withPicker={false} busy />));
    shot("without a picker", third.container);
  },
  "the line under the toolbar": async (shot, locale) => {
    const unavailable = parseUnavailable([{ code: "ja+en", available: false, reason: "missing_files" }], said(locale));
    const detection = (over: object): Detected => ({ detected: "ja", suggested: "ja", mixedUnavailable: null, confidence: 0.82, sure: true, ja: 0.82, en: 0.18, ...over }) as Detected;
    const cases: Record<string, { found: Detected | undefined; picked: "en" | "ja" | "ja+en"; playing?: boolean; experimentalPick?: boolean }> = {
      "japanese note": { found: undefined, picked: "ja" },
      "mixed note and the experimental hint, in the player": { found: undefined, picked: "ja+en", playing: true, experimentalPick: true },
      "detecting": { found: "running", picked: "en" },
      "sure, same language": { found: detection({}), picked: "ja" },
      "sure, another language": { found: detection({}), picked: "en" },
      "unsure": { found: detection({ sure: false, confidence: 0.4 }), picked: "ja" },
      "mixed": { found: detection({ detected: "ja+en", suggested: "ja+en", confidence: 0.7 }), picked: "ja" },
      "mixed that this machine cannot process": { found: detection({ detected: "ja+en", suggested: "ja", mixedUnavailable: "cpu" }), picked: "en" },
      "mostly Japanese, English picked": { found: detection({ detected: "ja+en", suggested: "ja" }), picked: "en" },
    };
    for (const [name, c] of Object.entries(cases)) {
      const { container, unmount } = render(
        wrap(locale, <SourceBar playing={c.playing ?? false} busy={false} sourceLang={c.picked} unavailable={unavailable} onSourceLang={() => undefined} found={c.found} experimentalPick={c.experimentalPick ?? false} />),
      );
      shot(name, container);
      unmount();
    }
    expect(typeof detectLine).toBe("function");
  },
  "the progress screen": async (shot, locale) => {
    const running = (step: string): JobView => reduceJob(WAITING, "progress", { step, fraction: 0.4, overall: 0.3 });
    const views: Record<string, [JobView, boolean]> = {
      waiting: [WAITING, false],
      "extracting audio": [running("audio"), false],
      "recognizing speech": [running("asr"), false],
      translating: [running("translate"), true],
      done: [reduceJob(WAITING, "done", { report: {} }), false],
    };
    for (const [name, [view, addsTarget]] of Object.entries(views)) {
      const { container, unmount } = render(wrap(locale, <ProgressBar view={view} target="Korean" addsTarget={addsTarget} />));
      shot(name, container);
      unmount();
    }
  },
};

const language = (code: string, name: string, native: string, quality = "stable") => ({ code, name, native_name: native, quality });
const target = (code: string, name: string, native: string, experimental = false) => ({ code, name, native_name: native, experimental });
const languagesReply = {
  default: "zh-TW",
  languages: [language("zh-TW", "Traditional Chinese", "繁體中文（台灣）"), language("en", "English", "English"), language("ko", "Korean", "한국어", "experimental")],
  sources: [
    { code: "en", available: true, targets: [target("zh-TW", "Traditional Chinese", "繁體中文（台灣）")] },
    { code: "ja", available: true, targets: [target("zh-TW", "Traditional Chinese", "繁體中文（台灣）"), target("ko", "Korean", "한국어", true)] },
    { code: "ja+en", available: false, reason: "cpu", targets: [target("zh-TW", "Traditional Chinese", "繁體中文（台灣）")] },
  ],
};
const projectReply = (over: object) => ({
  id: "p1",
  video_path: "C:/invented/p1.mp4",
  active_job: null,
  active_lang: "zh-TW",
  source_lang: "ja",
  steps: { translate: { status: "done" } },
  languages: { "zh-TW": { translate: { status: "done" } } },
  failed_cues: {},
  ...over,
});
const detectReply = { detected: "ja+en", suggested: "ja", mixed_unavailable: "cpu", confidence: 0.7, sure: true, shares: { ja: 0.7, en: 0.3 }, clear: 20, samples: [] };

function stubBackend(status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const method = init?.method ?? "GET";
      let body: unknown = {};
      if (path === "/api/languages/detect") body = detectReply;
      else if (path.startsWith("/api/languages")) body = languagesReply;
      else if (path === "/api/projects" && method === "POST") {
        if (status !== 200) return Promise.resolve(new Response(JSON.stringify({ detail: "The file is not there" }), { status }));
        body = mocks.project;
      } else if (path === "/api/projects") body = { projects: [] };
      else if (/\/subtitles/.test(path)) body = { cues: [] };
      else if (/\/edits/.test(path)) body = { ids: [] };
      else if (/\/playback/.test(path)) body = { position_s: 0, duration_s: 10, offset_ms: 0 };
      else if (/^\/api\/projects\/[^/]+$/.test(path)) body = mocks.project;
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

const queueItem = (over: Partial<BatchItem>): BatchItem => ({
  id: "i1",
  videoPath: "C:/invented/p1.mp4",
  projectId: "p1",
  lang: "ko",
  sourceLang: "ja",
  state: "running",
  position: 0,
  step: "translate",
  progress: 0.5,
  etaS: 700,
  attempts: 0,
  error: null,
  audioS: null,
  ...over,
});

const APP_SCREENS: Record<string, Screen> = {
  "the app while it starts": async (shot, locale) => {
    mocks.status = { kind: "starting" };
    const { container } = render(wrap(locale, <App />));
    shot("starting", container);
  },
  "the app when the backend fails": async (shot, locale) => {
    mocks.status = { kind: "failed", error: plainText("Port 1 is taken") };
    const { container } = render(wrap(locale, <App />));
    shot("failed", container);
  },
  "the app while it checks the models": async (shot, locale) => {
    mocks.checking = true;
    const { container } = render(wrap(locale, <App />));
    await screen.findByTestId("checking");
    shot("checking", container);
  },
  "the home screen with a queue chip and its toasts": async (shot, locale) => {
    mocks.batch = { ...EMPTY_BATCH, loaded: true, items: [queueItem({}), queueItem({ id: "i2", state: "done", etaS: null })] };
    const { container, rerender } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    shot("home", container);
    await waitFor(() => expect(screen.getByTestId("source-lang")).toBeTruthy());
    typeInto("video-path", "C:/invented/talk.mp4");
    await waitFor(() => expect(screen.getByTestId("source-note")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByTestId("detect-note")).toBeTruthy();
    expect(screen.queryByTestId("detect-hint")).toBeNull();
    shot("home with a detected language", container);
    mocks.batch = { ...(mocks.batch as Batch), items: [queueItem({ etaS: null })], finished: { n: 1, counts: { done: 2, failed: 1, cancelled: 1 } } };
    rerender(wrap(locale, <App />));
    await screen.findByTestId("toast");
    shot("queue finished", container);
    mocks.batch = { ...(mocks.batch as Batch), finished: { n: 2, counts: { done: 1, failed: 0, cancelled: 0 } } };
    rerender(wrap(locale, <App />));
    shot("queue finished, one", container);
    click("batch-open-add");
    click("stub-added");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("3"));
    shot("added to the queue", container);
  },
  "the home screen when an import fails": async (shot, locale) => {
    stubBackend(404);
    const { container } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/missing.mp4");
    click("import");
    await screen.findByTestId("error");
    shot("error", container);
  },
  "the processing screen and what follows": async (shot, locale) => {
    mocks.project = projectReply({ active_job: "j1", steps: {}, languages: {} });
    mocks.jobView = WAITING;
    const { container, rerender } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/p1.mp4");
    click("import");
    await screen.findByTestId("importing");
    shot("importing", container);
    mocks.jobView = reduceJob(WAITING, "progress", { step: "translate", fraction: 0.2, overall: 0.5 });
    rerender(wrap(locale, <App />));
    shot("importing, translating", container);
    mocks.project = projectReply({});
    mocks.jobView = { kind: "done", edits: { kept: 1, unmatched: 2 } };
    rerender(wrap(locale, <App />));
    await screen.findByTestId("player-stub");
    shot("played after an import: edits notice", within(container).getByTestId("stub-notice"));
    shot("header while playing", container.querySelector("header") as Element);
  },
  "the processing screen when it fails": async (shot, locale) => {
    mocks.project = projectReply({ active_job: "j1", steps: {}, languages: {} });
    mocks.jobView = WAITING;
    const { container, rerender } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/p1.mp4");
    click("import");
    await screen.findByTestId("importing");
    mocks.jobView = { kind: "failed", error: plainText("Out of memory") };
    rerender(wrap(locale, <App />));
    await screen.findByTestId("error");
    shot("failed", container);
  },
  "the processing screen when the connection drops": async (shot, locale) => {
    mocks.project = projectReply({ active_job: "j1", steps: {}, languages: {} });
    mocks.jobView = WAITING;
    const { container, rerender } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/p1.mp4");
    click("import");
    await screen.findByTestId("importing");
    mocks.jobView = reduceJob(reduceJob(WAITING, "progress", { step: "asr", fraction: 0.1, overall: 0.1 }), "disconnected", null);
    rerender(wrap(locale, <App />));
    await screen.findByTestId("error");
    shot("lost", container);
  },
  "the opened video: the notice and the blocked add": async (shot, locale) => {
    mocks.project = projectReply({});
    mocks.batch = { ...EMPTY_BATCH, loaded: true, items: [queueItem({})] };
    const { container } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/p1.mp4");
    click("import");
    await screen.findByTestId("player-stub");
    shot("notice and blocked", screen.getByTestId("player-stub"));
    shot("header", container.querySelector("header") as Element);
  },
  "the settings button, the library button and the drop hint": async (shot, locale) => {
    mocks.dropping = true;
    mocks.project = projectReply({});
    const { container } = render(wrap(locale, <App />));
    await screen.findByTestId("ready");
    await screen.findByTestId("drop-hint");
    shot("drop hint", container);
    mocks.dropping = false;
    typeInto("video-path", "C:/invented/p1.mp4");
    click("import");
    await screen.findByTestId("player-stub");
    shot("toolbar while a video is open", container.querySelector("header") as Element);
  },
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("vst.wizard.skipped", "1");
  mocks.status = { kind: "ready" };
  mocks.checking = false;
  mocks.dropping = false;
  mocks.batch = EMPTY_BATCH;
  mocks.jobView = WAITING;
  mocks.project = projectReply({});
  mocks.check = null;
  mocks.checkMode = "ok";
  mocks.download = null;
  stubBackend();
  Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: () => undefined });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ALL: Record<string, Screen> = { ...SCREENS, ...APP_SCREENS };
const recorded: Record<string, Record<string, Harvest>> = { "zh-TW": {}, en: {} };

describe.each(["zh-TW", "en"] as const)("W1 screens in %s", (locale) => {
  for (const [name, screenFn] of Object.entries(ALL)) {
    it(name, async () => {
      const seen: Record<string, Harvest> = {};
      const shot: Shot = (label, root) => {
        const element = root ?? document.body;
        seen[label] = harvest(element);
      };
      mocks.settings = { ...llmView(), uiLanguage: locale };
      await screenFn(shot, locale);
      expect(Object.keys(seen).length).toBeGreaterThan(0);
      recorded[locale]![name] = seen as never;
      if (locale === "en") {
        for (const [label, h] of Object.entries(seen)) {
          expect(NOT_ENGLISH.test(h.text), `${name} / ${label}: ${h.text}`).toBe(false);
          for (const a of h.attrs) expect(NOT_ENGLISH.test(a), `${name} / ${label}: ${a}`).toBe(false);
        }
        return;
      }
      if (WRITE) {
        written[name] = [seen as never];
        return;
      }
      const fixture = JSON.parse((await files()).readFileSync(FIXTURE, "utf-8")) as Record<string, [Record<string, Harvest>]>;
      expect(Object.keys(seen), name).toEqual(Object.keys(fixture[name]![0]!));
      for (const [label, h] of Object.entries(seen)) {
        const old = fixture[name]![0]![label]!;
        expect(h.text, `${name} / ${label}`).toBe(old.text);
        expect(h.attrs, `${name} / ${label}`).toEqual(old.attrs);
      }
    });
  }
});

afterAll(async () => {
  if (WRITE) (await files()).writeFileSync(FIXTURE, `${JSON.stringify(written, null, 1)}\n`, "utf-8");
});
