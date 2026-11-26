// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { EMPTY_BATCH } from "../batch/model";
import { ImportPanel } from "../import/ImportPanel";
import { licenses } from "../manage/screens.fixture";
import { ProgressBar } from "../progress/ProgressBar";
import { WAITING, reduceJob } from "../progress/job";
import { LicensesSection } from "../settings/LicensesSection";
import { SettingsBar } from "../settings/SettingsBar";
import { DEFAULTS } from "../settings/settings";
import { I18nProvider } from "./I18nProvider";
import type { Locale } from "./locale";

/**
 * The names of the languages, the window title and the platform examples, in each released language.
 * Traditional Chinese must equal what `main` showed (`w1b.screens.zh-TW.fixture.json`, written from
 * `main` with W1B_FIXTURE=write), and English must hold no Chinese, Japanese or Korean character.
 * The stubs carry the names the real backend sends (`native_name`), so a native name that reaches the
 * English render is a name the catalog did not translate.
 */

const mocks = vi.hoisted(() => ({ jobView: null as unknown, project: null as unknown, uiLanguage: "zh-TW" }));
const backend = { port: 1, token: "t" };

vi.mock("@tauri-apps/api/core", () => ({ convertFileSrc: (p: string) => p, invoke: () => Promise.resolve(null) }));
vi.mock("../api/backend", () => ({
  watchBackend: (onStatus: (s: unknown) => void) => {
    onStatus({ kind: "ready", backend: { port: 1, token: "t" } });
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
  fetchModelStates: () => Promise.resolve([]),
  fetchSettings: () => Promise.resolve({ uiLanguage: mocks.uiLanguage }),
  fetchLicenses: () => Promise.resolve(licenses),
  openUrl: () => Promise.resolve(),
  saveUiLanguage: () => Promise.resolve(),
}));
vi.mock("../batch/useBatch", () => ({ useBatch: () => EMPTY_BATCH }));
vi.mock("../batch/notify", () => ({ notifyWindows: () => Promise.resolve() }));
vi.mock("../summary/useSummary", () => ({ useSummary: () => null }));
vi.mock("../progress/useJob", () => ({ useJob: () => mocks.jobView }));
vi.mock("../import/useDrops", () => ({ useDrops: () => undefined }));
vi.mock("../player/Player", () => ({ Player: () => <div data-testid="player-stub" /> }));
vi.mock("../player/Library", () => ({ Library: () => null }));
vi.mock("../batch/BatchPanel", () => ({ BatchPanel: () => null }));
vi.mock("../batch/CountdownModal", () => ({ CountdownModal: () => null }));
vi.mock("../batch/AddDialog", () => ({ rowsFor: () => [], AddDialog: () => null }));

/** What `GET /api/languages` sends for every target (`backend/core/languages.py`): English name, native name. */
const NATIVE: Record<string, [string, string]> = {
  "zh-TW": ["Traditional Chinese (Taiwan)", "繁體中文（台灣）"],
  "zh-CN": ["Simplified Chinese", "简体中文"],
  en: ["English", "English"],
  ja: ["Japanese", "日本語"],
  ko: ["Korean", "한국어"],
  es: ["Spanish", "Español"],
  fr: ["French", "Français"],
  de: ["German", "Deutsch"],
  pt: ["Portuguese", "Português"],
  it: ["Italian", "Italiano"],
  ru: ["Russian", "Русский"],
  vi: ["Vietnamese", "Tiếng Việt"],
  th: ["Thai", "ไทย"],
  id: ["Indonesian", "Bahasa Indonesia"],
};
const CODES = Object.keys(NATIVE);
const targetOf = (code: string) => ({ code, name: NATIVE[code]![0], native_name: NATIVE[code]![1], experimental: code === "ko" });
const targetList = CODES.map((code) => ({ code, name: NATIVE[code]![0], nativeName: NATIVE[code]![1], experimental: code === "ko" }));
const languagesReply = {
  default: "zh-TW",
  languages: CODES.map((code) => ({ code, name: NATIVE[code]![0], native_name: NATIVE[code]![1], quality: "stable" })),
  sources: [{ code: "ja", available: true, targets: CODES.filter((c) => c !== "ja").map(targetOf) }],
};
const projectReply = {
  id: "p1",
  video_path: "C:/invented/p1.mp4",
  active_job: "j1",
  active_lang: "zh-TW",
  source_lang: "ja",
  steps: {},
  languages: {},
  failed_cues: {},
};

function stubBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const method = init?.method ?? "GET";
      let body: unknown = {};
      if (path === "/api/languages/detect") {
        body = { detected: "ja", suggested: "ja", mixed_unavailable: null, confidence: 0.9, sure: true, shares: { ja: 1 }, clear: 20, samples: [] };
      } else if (path.startsWith("/api/languages")) body = languagesReply;
      else if (path === "/api/projects" && method === "POST") body = projectReply;
      else if (path === "/api/projects") body = { projects: [] };
      else if (/^\/api\/projects\/[^/]+$/.test(path)) body = projectReply;
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

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

const CJK = /[\u3000-\u303f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]/;
const FIXTURE = "src/i18n/w1b.screens.zh-TW.fixture.json";
const WRITE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["W1B_FIXTURE"] === "write";
interface Files {
  readFileSync: (path: string, encoding: string) => string;
  writeFileSync: (path: string, data: string, encoding: string) => void;
}
const files = async () => (await import("node:fs" as string)) as Files;
const written: Record<string, Record<string, Harvest>> = {};

const shell = window as unknown as { __TAURI_INTERNALS__?: unknown };
const separator = (sep: string) => {
  shell.__TAURI_INTERNALS__ = { plugins: { path: { sep } } };
};
const typeInto = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });
const wrap = (locale: Locale, node: ReactNode) => <I18nProvider initial={locale}>{node}</I18nProvider>;

const importBox = (props: { targets?: typeof targetList; target?: string; withPicker?: boolean } = {}) => (
  <ImportPanel
    busy={false}
    sourceLang="ja"
    unavailable={{}}
    onSourceLang={() => undefined}
    targets={props.targets ?? []}
    target={props.target ?? "zh-TW"}
    onTarget={() => undefined}
    withPicker={props.withPicker ?? false}
    onImport={() => undefined}
    onPath={() => undefined}
  />
);

type Shot = (name: string, root?: Element) => void;
type Screen = (shot: Shot, locale: Locale) => Promise<void>;

const SCREENS: Record<string, Screen> = {
  "the title of the page": async (shot, locale) => {
    document.title = "字幕翻譯";
    render(wrap(locale, <p>x</p>));
    const holder = document.createElement("p");
    holder.setAttribute("title", document.title);
    shot("document title", holder);
  },
  "the subtitle language picker of the import header, for every language the backend offers": async (shot, locale) => {
    for (const code of CODES) {
      const { container, unmount } = render(wrap(locale, importBox({ targets: targetList, target: code, withPicker: true })));
      shot(`target ${code}`, container.querySelector("select[data-testid='target-lang']") as Element);
      unmount();
    }
    const one = render(wrap(locale, importBox({ targets: [targetList[0]!], withPicker: true })));
    shot("one target", one.container.querySelector("[data-testid='target-lang']") as Element);
  },
  "the progress screen, translating into each language": async (shot, locale) => {
    mocks.project = projectReply;
    for (const code of ["zh-TW", "ko", "es", "vi", "id"]) {
      mocks.jobView = reduceJob(WAITING, "progress", { step: "translate", fraction: 0.4, overall: 0.55 });
      const { container, unmount } = render(wrap(locale, <App />));
      await screen.findByTestId("ready");
      const picker = (await screen.findByTestId("target-lang")) as HTMLSelectElement;
      await screen.findByText(/Indonesian|Bahasa Indonesia/, { selector: "option" });
      fireEvent.change(picker, { target: { value: code } });
      typeInto("video-path", "C:/invented/p1.mp4");
      fireEvent.click(screen.getByTestId("import"));
      await screen.findByTestId("importing");
      shot(`importing into ${code}`, container.querySelector("[data-testid='importing']") as Element);
      unmount();
    }
  },
  "the subtitle bar of the player, naming the language": async (shot, locale) => {
    const { container } = render(wrap(locale, <SettingsBar langName="Korean" settings={DEFAULTS} onChange={() => undefined} />));
    shot("bar", container);
  },
  "the progress bar alone": async (shot, locale) => {
    const view = reduceJob(WAITING, "progress", { step: "translate", fraction: 0.4, overall: 0.55 });
    const { container } = render(wrap(locale, <ProgressBar view={view} target="Traditional Chinese" />));
    shot("translating", container);
  },
  "the import box on a PC": async (shot, locale) => {
    separator("\\");
    const { container } = render(wrap(locale, importBox()));
    shot("path box", container);
  },
  "the licenses page on a PC": async (shot, locale) => {
    separator("\\");
    const { container } = render(wrap(locale, <LicensesSection backend={backend} />));
    await screen.findByTestId("licenses-table");
    shot("notice", container.querySelector("[data-testid='bundled-notice']") as Element);
  },
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("vst.wizard.skipped", "1");
  mocks.jobView = WAITING;
  mocks.project = projectReply;
  stubBackend();
});
afterEach(() => {
  cleanup();
  delete shell.__TAURI_INTERNALS__;
  vi.unstubAllGlobals();
});

describe.each(["zh-TW", "en"] as const)("W1b screens in %s", (locale) => {
  for (const [name, screenFn] of Object.entries(SCREENS)) {
    it(name, async () => {
      const seen: Record<string, Harvest> = {};
      mocks.uiLanguage = locale;
      await screenFn((label, root) => {
        seen[label] = harvest(root ?? document.body);
      }, locale);
      expect(Object.keys(seen).length).toBeGreaterThan(0);
      if (locale === "en") {
        for (const [label, h] of Object.entries(seen)) {
          expect(CJK.test(h.text), `${name} / ${label}: ${h.text}`).toBe(false);
          for (const a of h.attrs) expect(CJK.test(a), `${name} / ${label}: ${a}`).toBe(false);
        }
        return;
      }
      if (WRITE) {
        written[name] = seen;
        return;
      }
      const fixture = JSON.parse((await files()).readFileSync(FIXTURE, "utf-8")) as Record<string, Record<string, Harvest>>;
      expect(Object.keys(seen), name).toEqual(Object.keys(fixture[name]!));
      for (const [label, h] of Object.entries(seen)) {
        expect(h.text, `${name} / ${label}`).toBe(fixture[name]![label]!.text);
        expect(h.attrs, `${name} / ${label}`).toEqual(fixture[name]![label]!.attrs);
      }
    });
  }
});

afterAll(async () => {
  if (WRITE) (await files()).writeFileSync(FIXTURE, `${JSON.stringify(written, null, 1)}\n`, "utf-8");
});

describe("what the English window says", () => {
  it("names each target language in English", () => {
    const { container } = render(wrap("en", importBox({ targets: targetList, withPicker: true })));
    const options = [...container.querySelectorAll("select[data-testid='target-lang'] option")].map((o) => o.textContent);
    expect(options).toEqual([
      "Traditional Chinese",
      "Simplified Chinese",
      "English",
      "Japanese",
      "Korean (experimental)",
      "Spanish",
      "French",
      "German",
      "Portuguese",
      "Italian",
      "Russian",
      "Vietnamese",
      "Thai",
      "Indonesian",
    ]);
  });

  it("says which language the progress screen translates into", async () => {
    mocks.uiLanguage = "en";
    mocks.jobView = reduceJob(WAITING, "progress", { step: "translate", fraction: 0.4, overall: 0.55 });
    render(wrap("en", <App />));
    await screen.findByTestId("ready");
    typeInto("video-path", "C:/invented/p1.mp4");
    fireEvent.click(screen.getByTestId("import"));
    await screen.findByTestId("importing");
    expect(screen.getByTestId("step-name").textContent).toBe("Translating into Traditional Chinese (5/7)");
  });

  it("titles the page in English", () => {
    render(wrap("en", <p>x</p>));
    expect(document.title).toBe("Video Subtitle Translator");
  });
});

describe("a Mac", () => {
  it("is shown a Mac path in the import box, in each language", () => {
    separator("/");
    expect(render(wrap("en", importBox())).getByTestId("video-path").getAttribute("placeholder")).toBe("Full path to the video, e.g. /Users/me/Movies/talk.mp4");
    cleanup();
    expect(render(wrap("zh-TW", importBox())).getByTestId("video-path").getAttribute("placeholder")).toBe("影片的完整路徑，例如 /Users/me/Movies/talk.mp4");
  });

  it("is told FFmpeg comes from Homebrew, not from an installer", async () => {
    separator("/");
    for (const locale of ["en", "zh-TW"] as const) {
      const { unmount } = render(wrap(locale, <LicensesSection backend={backend} />));
      await screen.findByTestId("licenses-table");
      const notice = screen.getByTestId("ffmpeg-notice");
      expect(notice.textContent).toContain("Homebrew");
      expect(notice.textContent).not.toMatch(/ffmpeg\.exe|DLL/);
      expect(notice.querySelector("a")?.getAttribute("href")).toBe("https://ffmpeg.org/legal.html");
      unmount();
    }
  });
});
