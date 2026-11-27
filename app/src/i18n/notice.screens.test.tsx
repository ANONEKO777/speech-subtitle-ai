// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { pickVideo, pickVideos, watchBackend, type BackendStatus } from "../api/backend";
import type { Backend } from "../api/client";
import { BatchPanel } from "../batch/BatchPanel";
import { EMPTY_BATCH, parseSnapshot } from "../batch/model";
import { burnViewOf } from "../api/library";
import { parseSelfTest } from "../manage/parse";
import { BurnCard } from "../player/Overlays";
import { SelfTestPanel } from "../settings/HardwareSection";
import { LicensesSection } from "../settings/LicensesSection";
import { UpdateSectionAlone } from "../settings/updateTestkit";
import { I18nProvider, useI18n } from "./I18nProvider";
import type { Locale } from "./locale";
import { NOT_ENGLISH } from "./notEnglish";
import fixture from "./notices.wire.fixture.json";
import shell from "./notices.shell.json";
import shellBefore from "./notices.shell.before.json";

/**
 * A backend or shell sentence is kept as it came and worded when it is shown, so a change of
 * language re-words it on the screen. The queue row's error is stored in `queue.db`, and a row an
 * earlier version stored has no notices and shows as it was.
 */

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(command: string, args?: unknown) => Promise<unknown>>(),
  listeners: new Map<string, (event: { payload: unknown }) => void>(),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: (name: string, handler: (event: { payload: unknown }) => void) => {
    tauri.listeners.set(name, handler);
    return Promise.resolve(() => undefined);
  },
}));
vi.mock("@tauri-apps/api/webview", () => ({
  getCurrentWebview: () => ({ onDragDropEvent: () => Promise.resolve(() => undefined) }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  tauri.invoke.mockReset();
  tauri.listeners.clear();
  localStorage.clear();
});

const backend = { port: 1, token: "t" } as Backend;
const scenario = (name: keyof typeof fixture) => fixture[name];

let change: (locale: Locale) => void = () => undefined;
function Switch({ children }: { children: ReactNode }) {
  const i18n = useI18n()!;
  change = i18n.setUiLanguage;
  return <>{children}</>;
}
const show = (node: ReactNode, initial: Locale = "zh-TW") =>
  render(
    <I18nProvider initial={initial}>
      <Switch>{node}</Switch>
    </I18nProvider>,
  );
const switchTo = (locale: Locale) => act(() => change(locale));

const OLD = "OptionsError: 這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64）。";
const row = (id: string, error: object) => ({
  id,
  video_path: `C:/videos/${id}.mp4`,
  project_id: id,
  target_lang: "zh-TW",
  state: "failed",
  position: id === "new" ? 0 : 1,
  ...error,
});

describe("a queue row's stored error", () => {
  it("follows a change of language, and one an earlier version stored shows as it was", () => {
    const stored = scenario("localBuild");
    const { items } = parseSnapshot({
      items: [
        row("new", { last_error: `OptionsError: ${stored.text}`, last_error_notices: stored.notices }),
        row("old", { last_error: OLD }),
      ],
    });
    show(<BatchPanel backend={backend} batch={{ ...EMPTY_BATCH, loaded: true, link: "live", items }} languages={[]} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />);
    const shown = (id: string) => screen.getByTestId(`qerror-${id}`).textContent!;
    expect(shown("new")).toContain(`OptionsError: ${stored.before}`);
    expect(shown("old")).toContain(OLD);

    switchTo("en");

    expect(shown("new")).toContain(`OptionsError: ${stored.text}`);
    expect(shown("new")).not.toMatch(NOT_ENGLISH);
    expect(shown("old")).toContain(OLD);

    switchTo("zh-TW");

    expect(shown("new")).toContain(`OptionsError: ${stored.before}`);
  });
});

describe("a self-test that fails for want of the Visual C++ runtime", () => {
  it("words the result and each stage, with the message nested in the report's sentence", () => {
    const [message, stage] = [scenario("selftest.gpu.message"), scenario("selftest.gpu.stage")];
    const result = parseSelfTest({
      ok: false,
      device: "cpu",
      stages: [{ stage: "asr", runtime_id: "whispercpp", device: "cpu", installed: true, ok: false, seconds: 0.1, detail: stage.text, detail_notices: stage.notices }],
      fallback: null,
      seconds: 0.1,
      message: message.text,
      message_notices: message.notices,
    });
    show(<SelfTestPanel result={result} running={false} />);
    const body = () => screen.getByTestId("selftest-body").textContent;
    const stages = () => screen.getByTestId("selftest-result").querySelector("li")!.textContent;
    const vc = scenario("vc").before;
    const gpu = `ASR (whispercpp-b5454-win-cuda12.4): ${vc}; LLM (llama.cpp-b12068-win-cuda12.4): ${vc}`;
    const cpu = `ASR (whispercpp-b5454-win-cpu): ${vc}; LLM (llama.cpp-b12068-win-cpu): ${vc}`;
    expect(body()).toBe(`GPU 後端失敗（${gpu}），改用 CPU 後端。但 CPU 後端也無法使用（${cpu}）。`);
    expect(stages()).toContain(stage.before);

    switchTo("en");

    expect(body()).toBe(message.text);
    expect(stages()).toContain(stage.text);
    expect(screen.getByTestId("selftest-result").textContent).not.toMatch(NOT_ENGLISH);
  });
});

describe("a burn that failed", () => {
  it("words the card in the window's language, and again after a change", () => {
    const failed = scenario("encoder.windows");
    const view = burnViewOf({ id: "b", state: "failed", percent: 4, output: "o.mp4", error: failed.text, error_notices: failed.notices });
    show(<BurnCard view={view} error={view.error} onCancel={() => undefined} />);
    expect(screen.getByTestId("burn-progress").textContent).toContain(failed.before);

    switchTo("en");

    expect(screen.getByTestId("burn-progress").textContent).toContain(failed.text);
    expect(screen.getByTestId("burn-progress").textContent).not.toMatch(NOT_ENGLISH);
  });
});

describe("a refused request on a settings page", () => {
  it("shows the notices of the reply in the window's language", async () => {
    const refused = scenario("cloudKey");
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({ detail: refused.text, notices: refused.notices }), { status: 422 })));
    show(<LicensesSection backend={backend} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe(refused.before));

    switchTo("en");

    expect(screen.getByRole("alert").textContent).toBe(refused.text);
  });
});

describe("what the shell rejects a command with", () => {
  it("is worded on the update page, and again after a change", async () => {
    const message = shell["shell.update.unreachable"].english;
    tauri.invoke.mockRejectedValue({ message, notices: [{ code: "shell.update.unreachable", params: {}, message }] });
    show(<UpdateSectionAlone />);
    fireEvent.click(screen.getByTestId("update-check"));
    await waitFor(() => expect(screen.getByTestId("update-failed").textContent).toBe(shellBefore["shell.update.unreachable"]));

    switchTo("en");

    expect(screen.getByTestId("update-failed").textContent).toBe(message);
  });
});

/** A job's event stream, which the test feeds what the backend would send. */
class JobStream {
  static open: JobStream | null = null;
  onerror: (() => void) | null = null;
  private readonly handlers = new Map<string, (event: { data: string }) => void>();
  constructor() {
    JobStream.open = this;
  }
  addEventListener(name: string, handler: (event: { data: string }) => void) {
    this.handlers.set(name, handler);
  }
  close() {}
  send(name: string, data: unknown) {
    act(() => this.handlers.get(name)!({ data: JSON.stringify(data) }));
  }
}

/** The whole window with a ready backend, on which a person imports a video that is not translated yet. */
async function importVideo(startJob: { status: number; body: unknown }) {
  const project = { id: "p1", video_path: "C:/videos/talk.mp4", active_job: null, steps: {}, languages: {} };
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const call = `${init?.method ?? "GET"} ${new URL(url).pathname}`;
    const found =
      call === "POST /api/projects" ? { status: 200, body: project } : call === "POST /api/projects/p1/jobs" ? startJob : { status: 404, body: {} };
    return Promise.resolve(new Response(JSON.stringify(found.body), { status: found.status }));
  });
  vi.stubGlobal("EventSource", JobStream);
  tauri.invoke.mockImplementation((command) => Promise.resolve(command === "backend_info" ? backend : null));
  show(<App />);
  fireEvent.change(screen.getByTestId("video-path"), { target: { value: project.video_path } });
  await waitFor(() => expect(screen.getByTestId("import")).toHaveProperty("disabled", false));
  fireEvent.click(screen.getByTestId("import"));
}

describe("the window's own failure screens", () => {
  afterEach(() => {
    JobStream.open = null;
  });

  const inBothLanguages = (testId: string, zhTW: string, english: string) => {
    const shown = () => screen.getByTestId(testId).textContent;
    expect(shown()).toBe(zhTW);

    switchTo("en");

    expect(shown()).toBe(english);
    expect(shown()).not.toMatch(NOT_ENGLISH);
  };

  it("words the error of a job that fails while the video is processed", async () => {
    const failed = scenario("vc");
    await importVideo({ status: 202, body: { id: "j1" } });
    await waitFor(() => expect(JobStream.open).not.toBeNull());

    JobStream.open!.send("failed", { step: "asr", error: `asr: ${failed.text}`, error_notices: failed.notices });

    await screen.findByTestId("error");
    inBothLanguages("error", `處理失敗：asr: ${failed.before}`, `Processing failed: asr: ${failed.text}`);
  });

  it("words the refusal of an import that cannot start", async () => {
    const refused = scenario("vc");

    await importVideo({ status: 422, body: { detail: refused.text, notices: refused.notices } });

    await screen.findByTestId("error");
    inBothLanguages("error", refused.before, refused.text);
  });

  it("words why the backend failed to start, with the backend's own sentence inside the shell's", async () => {
    const platform = scenario("platform.linux");
    const exited = "shell.backend.exitedEarly";
    const message = shell[exited].english.replace("{detail}", () => `error: ${platform.text}`);
    const notices = [{ code: exited, params: { detail: `error: ${platform.text}` }, message }, ...platform.notices];
    tauri.invoke.mockResolvedValue(null);
    show(<App />);
    await waitFor(() => expect(tauri.listeners.has("backend-failed")).toBe(true));

    act(() => tauri.listeners.get("backend-failed")!({ payload: { message, notices } }));

    inBothLanguages("backend-failed", shellBefore[exited].replace("{detail}", () => `error: ${platform.before}`), message);
  });
});

describe("the shell contract", () => {
  it("hands the window the backend-failed payload with its notices", async () => {
    tauri.invoke.mockResolvedValue(null);
    const seen: BackendStatus[] = [];
    await watchBackend((status) => seen.push(status));
    const message = shell["shell.backend.stopped"].english;
    const notices = [{ code: "shell.backend.stopped", params: {}, message }];

    tauri.listeners.get("backend-failed")!({ payload: { message, notices } });

    expect(seen).toEqual([{ kind: "failed", error: { text: message, notices } }]);
  });

  it("names the file dialog's filter, under the name the shell's commands read", async () => {
    tauri.invoke.mockResolvedValue(null);

    await pickVideo("Videos and audio");
    await pickVideos("影片與音訊");

    expect(tauri.invoke.mock.calls).toEqual([
      ["pick_video", { filterName: "Videos and audio" }],
      ["pick_videos", { filterName: "影片與音訊" }],
    ]);
  });
});
