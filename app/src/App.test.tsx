// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EMPTY_BATCH, type Batch, type BatchItem } from "./batch/model";
import { tZhTW } from "./i18n";

const backend = { port: 1, token: "t" };
let batch: Batch = EMPTY_BATCH;
let models: { kind: string; state: string }[] = [];

vi.mock("@tauri-apps/api/core", () => ({ convertFileSrc: (p: string) => p, invoke: () => Promise.resolve(null) }));
vi.mock("./api/backend", () => ({
  watchBackend: (onStatus: (s: unknown) => void) => {
    onStatus({ kind: "ready", backend });
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
vi.mock("./batch/useBatch", () => ({ useBatch: () => batch }));
vi.mock("./batch/notify", () => ({ notifyWindows: () => Promise.resolve() }));
vi.mock("./manage/api", async (orig) => ({ ...(await orig<typeof import("./manage/api")>()), fetchModelStates: () => Promise.resolve(models) }));
vi.mock("./summary/useSummary", () => ({ useSummary: () => null }));
import { App } from "./App";

const target = (code: string, name: string, native: string, experimental = false) => ({ code, name, native_name: native, experimental });
const languages = {
  default: "zh-TW",
  languages: [
    { code: "zh-TW", name: "Traditional Chinese", native_name: "繁體中文（台灣）", quality: "stable" },
    { code: "en", name: "English", native_name: "English", quality: "stable" },
    { code: "ko", name: "Korean", native_name: "한국어", quality: "experimental" },
  ],
  sources: [
    { code: "en", available: true, targets: [target("zh-TW", "Traditional Chinese", "繁體中文（台灣）")] },
    {
      code: "ja",
      available: true,
      targets: [target("zh-TW", "Traditional Chinese", "繁體中文（台灣）"), target("en", "English", "English"), target("ko", "Korean", "한국어", true)],
    },
  ],
};
const steps = (lang: string) => ({ [lang]: { translate: { status: "done" } } });
const project = (id: string) => ({
  id,
  video_path: `C:/invented/${id}.mp4`,
  active_job: null,
  active_lang: "zh-TW",
  source_lang: "ja",
  steps: { translate: { status: "done" } },
  languages: { ...steps("zh-TW"), ...steps("en") },
  failed_cues: {},
});
const cue = { id: 1, start_ms: 0, end_ms: 1000, src: "こんにちは。", lang: "ja", zh: "你好。", en: "こんにちは。" };

const reply = (path: string, method: string): unknown => {
  if (path.startsWith("/api/languages")) return languages;
  if (path === "/api/projects" && method === "POST") return project("p1");
  if (path === "/api/projects") return { projects: [] };
  if (/^\/api\/projects\/[^/]+\/subtitles/.test(path)) return { cues: [cue] };
  if (/^\/api\/projects\/[^/]+\/edits/.test(path)) return { ids: [] };
  if (/^\/api\/projects\/[^/]+\/playback/.test(path)) return { position_s: 0, duration_s: 10, offset_ms: 0 };
  if (/^\/api\/projects\/[^/]+$/.test(path)) return project("p1");
  return {};
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("vst.wizard.skipped", "1");
  batch = EMPTY_BATCH;
  models = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(new Response(JSON.stringify(reply(new URL(url).pathname + new URL(url).search.replace(/\?.*/, ""), init?.method ?? "GET")), { status: 200 })),
    ),
  );
  Object.defineProperty(HTMLVideoElement.prototype, "requestVideoFrameCallback", { configurable: true, value: () => 1 });
  Object.defineProperty(HTMLVideoElement.prototype, "cancelVideoFrameCallback", { configurable: true, value: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: () => Promise.resolve() });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const item = (over: Partial<BatchItem>): BatchItem => ({
  id: "i1",
  videoPath: "C:/invented/p1.mp4",
  projectId: "p1",
  lang: "ko",
  sourceLang: "ja",
  state: "running",
  position: 0,
  step: "translate",
  progress: 0.5,
  etaS: null,
  attempts: 0,
  error: null,
  audioS: null,
  ...over,
});

const pick = (testId: string, value: string) => fireEvent.change(screen.getByTestId(testId), { target: { value } });

async function openProject() {
  render(<App />);
  await waitFor(() => expect(screen.getByTestId("source-lang")).toBeTruthy());
  pick("source-lang", "ja");
  await waitFor(() => expect(screen.getByTestId("target-lang").tagName).toBe("SELECT"));
  fireEvent.change(screen.getByTestId("video-path"), { target: { value: "C:/invented/p1.mp4" } });
  fireEvent.click(screen.getByTestId("import"));
  return screen.findByTestId("add-target");
}

describe("the home toolbar", () => {
  it("tells a person that an experimental subtitle language is not judged, and stops once another is picked", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("source-lang")).toBeTruthy());
    pick("source-lang", "ja");
    await waitFor(() => expect(screen.getByTestId("target-lang").tagName).toBe("SELECT"));
    expect(screen.queryByTestId("target-hint")).toBeNull();
    pick("target-lang", "ko");
    expect((await screen.findByTestId("target-hint")).textContent).toBe(tZhTW("targets.experimentalHint"));
    pick("target-lang", "en");
    await waitFor(() => expect(screen.queryByTestId("target-hint")).toBeNull());
  });
});

describe("adding a subtitle language to the open project", () => {
  it("is possible when nothing runs", async () => {
    const add = await openProject();
    expect((add as HTMLButtonElement).disabled).toBe(false);
  });

  it("is blocked, with the reason, while the queue translates this project", async () => {
    batch = { ...EMPTY_BATCH, loaded: true, items: [item({})] };
    const add = (await openProject()) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    expect(add.title).toBe("這部影片正在處理中，等它完成後才能新增字幕語言");
  });

  it("is not blocked by a job of another video", async () => {
    batch = { ...EMPTY_BATCH, loaded: true, items: [item({ projectId: "other", videoPath: "C:/invented/other.mp4" })] };
    expect(((await openProject()) as HTMLButtonElement).disabled).toBe(false);
  });

  it("is not blocked by a job of this video that has not started", async () => {
    batch = { ...EMPTY_BATCH, loaded: true, items: [item({ state: "queued", step: null })] };
    expect(((await openProject()) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("a window whose storage throws", () => {
  it("still opens, plays a project and changes the volume", async () => {
    models = [
      { kind: "asr", state: "installed" },
      { kind: "llm", state: "installed" },
    ];
    const blocked = () => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    };
    const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(blocked);
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(blocked);
    await openProject();
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
    fireEvent.volumeChange(video!);
    expect(read).toHaveBeenCalled();
    expect(write).toHaveBeenCalled();
    expect(screen.getByTestId("add-target")).toBeTruthy();
  });
});
