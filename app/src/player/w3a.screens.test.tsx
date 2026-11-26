// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps, ReactNode } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LibraryItem } from "../api/library";
import { I18nProvider, useI18n } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import { DEFAULTS } from "../settings/settings";
import { Library } from "./Library";
import { BurnCard } from "./Overlays";
import { Player } from "./Player";

/**
 * The player (W3a) rendered in each released language. Traditional Chinese must equal what the player said
 * before the catalog (`w3a.screens.zh-TW.fixture.json`, written from `main` with W3A_FIXTURE=write), and
 * English must hold no Chinese or Japanese character. The stubs hold Latin text only, so a CJK character
 * on the English render is text the catalog did not carry. The export menu button is W3b's and is left out.
 */

const mocks = vi.hoisted(() => ({
  summary: null as { text: string; degraded: boolean } | null,
  still: "ok" as "ok" | "fail",
  clipboard: "ok" as "ok" | "fail",
  pick: "fail" as "ok" | "fail",
  folder: "fail" as "ok" | "fail",
  pip: "ok" as "ok" | "fail",
  burn: "done" as "done" | "failed" | "cancelled",
}));

vi.mock("@tauri-apps/api/core", () => ({ convertFileSrc: (p: string) => p, invoke: () => Promise.resolve(null) }));
vi.mock("../api/backend", () => ({
  openFolder: () => (mocks.folder === "ok" ? Promise.resolve() : Promise.reject(new Error("no such folder"))),
  pickFolder: () => (mocks.pick === "ok" ? Promise.resolve("C:/Shots") : Promise.reject(new Error("dialog refused"))),
  saveExport: () => Promise.resolve(null),
}));
vi.mock("../api/library", async (orig) => ({
  ...(await orig<typeof import("../api/library")>()),
  putPlayback: () => Promise.resolve({ positionS: 0, durationS: 0, offsetMs: 0 }),
  fetchFrameRate: () => Promise.resolve(30),
  fetchThumbnail: () => Promise.resolve(null),
  takeStill: () => (mocks.still === "ok" ? Promise.resolve({ path: "C:/Shots/still.png", png: new Blob() }) : Promise.reject(new Error("ffmpeg stopped"))),
  startBurn: () => Promise.resolve({ id: "b1", state: "running", percent: 10, output: "", error: null }),
  fetchBurn: () =>
    Promise.resolve(
      mocks.burn === "done"
        ? { id: "b1", state: "done", percent: 100, output: "C:/Shots/out.mp4", error: null }
        : mocks.burn === "failed"
          ? { id: "b1", state: "failed", percent: 40, output: "", error: "disk full" }
          : { id: "b1", state: "cancelled", percent: 40, output: "", error: null },
    ),
  cancelBurn: () => Promise.resolve(),
}));
vi.mock("../summary/useSummary", () => ({ useSummary: () => mocks.summary }));

const ATTRS = ["title", "aria-label", "placeholder", "alt", "label"] as const;
interface Harvest {
  readonly text: string;
  readonly attrs: readonly string[];
}

/** The export menu button holds W3b's text, so every harvest leaves it out. */
const W3B = '[data-testid="export-menu"]';

function harvest(root: Element): Harvest {
  const copy = root.cloneNode(true) as Element;
  for (const node of copy.querySelectorAll(W3B)) node.remove();
  const text = (copy.textContent ?? "").replace(/\s+/g, " ").trim();
  const attrs: string[] = [];
  for (const node of [copy, ...copy.querySelectorAll("*")]) {
    for (const name of ATTRS) {
      const value = node.getAttribute(name);
      if (value) attrs.push(`${name}=${value}`);
    }
  }
  return { text, attrs };
}

const CJK = /[\u3000-\u303f\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]/;

const FIXTURE = "src/player/w3a.screens.zh-TW.fixture.json";
const WRITE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["W3A_FIXTURE"] === "write";
interface Files {
  readFileSync: (path: string, encoding: string) => string;
  writeFileSync: (path: string, data: string, encoding: string) => void;
}
const files = async () => (await import("node:fs" as string)) as Files;
const written: Record<string, Harvest[]> = {};

const backend = { port: 1, token: "t" };
const cues = [
  { id: 1, startMs: 0, endMs: 4000, src: "Hello there.", lang: "ja", zh: "Hello." },
  { id: 2, startMs: 4000, endMs: 8000, src: "Thank you.", lang: "ja", zh: "" },
  { id: 3, startMs: 8000, endMs: 12000, src: "Goodbye.", lang: "en", zh: "Bye." },
];
const languages = [
  { code: "zh-TW", name: "Traditional Chinese (Taiwan)", nativeName: "Chinese (Taiwan)", quality: "stable" as const },
  { code: "ko", name: "Korean", nativeName: "Korean language", quality: "experimental" as const },
];
const addable = [
  { code: "en", name: "English", nativeName: "English text", experimental: false },
  { code: "es", name: "Spanish", nativeName: "Spanish text", experimental: true },
];

type PlayerProps = ComponentProps<typeof Player>;
const playerProps = (over: Partial<PlayerProps> = {}): PlayerProps => ({
  backend,
  projectId: "p1",
  videoPath: "C:/invented/a-very-long-video-name-that-goes-on-and-on-for-a-while-talk.mkv",
  sourceLang: "ja",
  settings: DEFAULTS,
  onSettings: () => undefined,
  languages,
  lang: "ko",
  onLang: () => undefined,
  experimental: new Set(["ko"]),
  addable,
  onAddTarget: () => undefined,
  addBlocked: null,
  failures: { failed: [2, 3], english: [3] },
  loaded: { cues, editedIds: [1] },
  notice: null,
  playback: { positionS: 0, durationS: 120, offsetMs: 0 },
  hasPrevVideo: true,
  hasNextVideo: true,
  onStep: () => undefined,
  library: <p>library stub</p>,
  batch: <p>queue stub</p>,
  batchBadge: "2",
  batchRequest: 0,
  ...over,
});

const item = (over: Partial<LibraryItem>): LibraryItem => ({
  id: "a",
  videoPath: "C:/invented/a.mp4",
  title: "a.mp4",
  exists: true,
  langs: ["zh-TW"],
  sourceLang: "ja",
  durationS: 600,
  positionS: 0,
  openedAtMs: 0,
  ...over,
});
const libraryProps = (items: readonly LibraryItem[], queue = { ids: [] as string[], current: null as string | null }): ComponentProps<typeof Library> => ({
  backend,
  items,
  queue,
  currentId: "a",
  names: new Map([["zh-TW", "Chinese"], ["ko", "Korean"]]),
  onPlay: () => undefined,
  onEnqueue: () => undefined,
  onDequeue: () => undefined,
  onQueueAll: () => undefined,
});

const click = (id: string) => fireEvent.click(screen.getByTestId(id));
const press = (key: string, mods: { ctrlKey?: boolean; shiftKey?: boolean } = {}) => fireEvent.keyDown(window, { key, ...mods });
const wrap = (locale: Locale, node: ReactNode) => <I18nProvider initial={locale}>{node}</I18nProvider>;
const video = () => screen.getByTestId("video") as HTMLVideoElement;
const osd = () => screen.getByTestId("osd");

type Shot = (name: string, root?: Element) => void;
type Screen = (shot: Shot, locale: Locale) => Promise<void>;

const loaded = async (locale: Locale, over: Partial<PlayerProps> = {}) => {
  const view = render(wrap(locale, <Player {...playerProps(over)} />));
  Object.defineProperty(video(), "duration", { configurable: true, value: 120 });
  fireEvent(video(), new Event("durationchange"));
  return view;
};

const SCREENS: Record<string, Screen> = {
  "the control bar and its menus": async (shot, locale) => {
    const { container } = await loaded(locale);
    shot("bar", container);
    click("ctl-speed");
    shot("speed menu", container);
    click("ctl-speed");
    click("ctl-offset");
    shot("offset popup", container);
    click("ctl-offset");
    click("ctl-more");
    shot("more menu", container);
    click("ctl-more");
    fireEvent.play(video());
    shot("playing", container);
    video().muted = true;
    fireEvent(video(), new Event("volumechange"));
    shot("muted", container);
  },
  "the control bar with the options turned on": async (shot, locale) => {
    const { container } = await loaded(locale, { settings: { ...DEFAULTS, burnShots: true, outputDir: "C:/Shots" }, hasPrevVideo: false, hasNextVideo: false });
    click("ctl-more");
    shot("more menu, burn on, folder set", container);
    click("ctl-more");
    click("ctl-offset");
    shot("offset popup, no offset", container);
  },
  "the help overlay": async (shot, locale) => {
    const { container } = await loaded(locale);
    press("?");
    await screen.findByTestId("help");
    shot("help", container);
    click("help-close");
    expect(screen.queryByTestId("help")).toBeNull();
    click("ctl-more");
    click("opt-help");
    await screen.findByTestId("help");
    shot("help from the more menu", screen.getByTestId("help"));
  },
  "the lines the player says over the video": async (shot, locale) => {
    const { container } = await loaded(locale);
    const say = (label: string, key: string, mods: { ctrlKey?: boolean; shiftKey?: boolean } = {}) => {
      press(key, mods);
      shot(label, osd());
    };
    say("seek forward", "ArrowRight");
    say("seek back", "j");
    say("seek to a part", "5");
    say("volume up", "ArrowUp");
    say("mute", "m");
    say("unmute", "m");
    say("speed up", "]");
    say("speed down", "[");
    say("next frame", ".");
    say("previous frame", ",");
    video().currentTime = 20;
    say("loop A", "a");
    video().currentTime = 40;
    say("loop A-B", "a");
    say("loop off", "a");
    say("offset later", "x");
    say("offset later again", "x");
    say("offset earlier", "z");
    say("offset earlier, below zero", "z");
    say("offset earlier, further below zero", "z");
    video().currentTime = 0;
    say("next subtitle", "ArrowRight", { ctrlKey: true });
    video().currentTime = 6;
    say("previous subtitle", "ArrowLeft", { ctrlKey: true });
    video().currentTime = 100;
    say("no next subtitle", "ArrowRight", { ctrlKey: true });
    video().currentTime = 0;
    say("no previous subtitle", "ArrowLeft", { ctrlKey: true });
    click("ctl-speed");
    click("speed-1.5");
    shot("speed from the menu", osd());
    expect(container).toBeTruthy();
  },
  "the toasts": async (shot, locale) => {
    const { container } = await loaded(locale, { playback: { positionS: 60, durationS: 120, offsetMs: 0 } });
    fireEvent(video(), new Event("loadedmetadata"));
    await screen.findByTestId("toast");
    shot("resumed", screen.getByTestId("toast"));
    click("toast-action");
    expect(screen.queryByTestId("toast")).toBeNull();

    const write = vi.fn(() => (mocks.clipboard === "ok" ? Promise.resolve() : Promise.reject(new Error("denied"))));
    vi.stubGlobal("ClipboardItem", class {});
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { write } });
    mocks.still = "ok";
    mocks.clipboard = "ok";
    click("ctl-shot");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("still.png"));
    shot("screenshot saved and copied", screen.getByTestId("toast"));
    mocks.folder = "fail";
    click("toast-action");
    await waitFor(() => expect(screen.getByTestId("toast").getAttribute("data-error")).toBe("true"));
    shot("open folder failed", screen.getByTestId("toast"));
    mocks.clipboard = "fail";
    click("ctl-shot");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("still.png"));
    shot("screenshot saved, not copied", screen.getByTestId("toast"));
    mocks.still = "fail";
    click("ctl-shot");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("ffmpeg stopped"));
    shot("screenshot failed", screen.getByTestId("toast"));

    Object.defineProperty(video(), "requestPictureInPicture", { configurable: true, value: () => (mocks.pip === "ok" ? Promise.resolve({}) : Promise.reject(new Error("not allowed"))) });
    mocks.pip = "ok";
    click("ctl-pip");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent?.length).toBeGreaterThan(0));
    shot("picture-in-picture", screen.getByTestId("toast"));
    mocks.pip = "fail";
    click("ctl-pip");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("not allowed"));
    shot("picture-in-picture failed", screen.getByTestId("toast"));

    const stage = screen.getByTestId("stage");
    Object.defineProperty(stage, "requestFullscreen", { configurable: true, value: () => Promise.reject(new Error("blocked")) });
    click("ctl-fs");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("blocked"));
    shot("full screen failed", screen.getByTestId("toast"));

    click("ctl-more");
    mocks.pick = "fail";
    click("opt-folder");
    await waitFor(() => expect(screen.getByTestId("toast-text").textContent).toContain("dialog refused"));
    shot("choosing the folder failed", screen.getByTestId("toast"));
    expect(container).toBeTruthy();
  },
  "the burned-in export": async (shot, locale) => {
    const { container } = await loaded(locale);
    click("export-menu");
    shot("full and clip entries", screen.getByTestId("export-burn-full"));
    shot("clip entry", screen.getByTestId("export-burn-clip"));
    click("export-burn-full");
    await screen.findByTestId("burn-progress");
    shot("progress", screen.getByTestId("burn-progress"));
    mocks.burn = "done";
    mocks.folder = "ok";
    await waitFor(() => expect(screen.getByTestId("toast")).toBeTruthy(), { timeout: 3000 });
    shot("done", screen.getByTestId("toast"));
    click("export-menu");
    mocks.burn = "failed";
    click("export-burn-clip");
    await waitFor(() => expect(screen.getByTestId("toast").getAttribute("data-error")).toBe("true"), { timeout: 3000 });
    shot("failed", screen.getByTestId("toast"));
    click("export-menu");
    mocks.burn = "cancelled";
    click("export-burn-full");
    await waitFor(() => expect(screen.getByTestId("toast").getAttribute("data-error")).toBe("false"), { timeout: 3000 });
    shot("cancelled", screen.getByTestId("toast"));
    expect(container).toBeTruthy();
  },
  "the progress card of a burn": async (shot, locale) => {
    const running = { id: "b", state: "running" as const, percent: 42, output: "", error: null };
    const first = render(wrap(locale, <BurnCard view={running} error={null} onCancel={() => undefined} />));
    shot("running", first.container);
    first.unmount();
    const second = render(wrap(locale, <BurnCard view={null} error="ffmpeg stopped" onCancel={() => undefined} />));
    shot("error", second.container);
  },
  "a video the player cannot play": async (shot, locale) => {
    await loaded(locale);
    fireEvent.error(video());
    await screen.findByTestId("unplayable");
    shot("unplayable", screen.getByTestId("unplayable"));
  },
  "the side column: subtitles, failures and edits": async (shot, locale) => {
    const { container } = await loaded(locale);
    shot("cue list", container);
    click("failed-filter");
    shot("only the failed ones", container);
    click("add-target");
    shot("add a language menu", container);
    click("add-target");
    cleanup();
    const second = await loaded(locale, { addBlocked: "A job is running", failures: undefined, loaded: { cues, editedIds: [1, 2] } });
    shot("blocked add, two edits, no failures", second.container);
  },
  "the side column: other tabs": async (shot, locale) => {
    mocks.summary = { text: "Overview of the talk", degraded: true };
    const { container } = await loaded(locale, { loaded: { cues, editedIds: [] }, failures: undefined });
    shot("no edits", container);
    click("tab-summary");
    shot("summary, degraded", container);
    click("tab-library");
    shot("library tab", container);
    click("tab-queue");
    shot("queue tab", container);
  },
  "the library": async (shot, locale) => {
    const first = render(wrap(locale, <Library {...libraryProps([])} />));
    shot("empty", first.container);
    first.unmount();
    const items = [
      item({ id: "a", title: "A talk with a very long title that keeps going and going on the same line.mp4", positionS: 300, openedAtMs: 5, langs: ["zh-TW", "ko"] }),
      item({ id: "b", title: "b.mp4", exists: false, sourceLang: "ja+en", openedAtMs: 4 }),
      item({ id: "c", title: "c.mp4", sourceLang: "en", durationS: 0 }),
    ];
    const second = render(wrap(locale, <Library {...libraryProps(items, { ids: ["a", "b", "gone"], current: "a" })} />));
    shot("with a queue, recent and all", second.container);
    second.unmount();
    const third = render(wrap(locale, <Library {...libraryProps(items)} />));
    shot("without a queue", third.container);
  },
};

beforeEach(() => {
  localStorage.clear();
  mocks.summary = null;
  mocks.pick = "fail";
  mocks.folder = "fail";
  mocks.pip = "ok";
  mocks.burn = "done";
  Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: () => Promise.resolve() });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "requestVideoFrameCallback", { configurable: true, value: () => 1 });
  Object.defineProperty(HTMLMediaElement.prototype, "cancelVideoFrameCallback", { configurable: true, value: () => undefined });
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const recorded: Record<string, Record<string, Harvest>> = { "zh-TW": {}, en: {} };

describe.each(["zh-TW", "en"] as const)("W3a screens in %s", (locale) => {
  for (const [name, screenFn] of Object.entries(SCREENS)) {
    it(name, async () => {
      const seen: Record<string, Harvest> = {};
      const shot: Shot = (label, root) => {
        seen[label] = harvest(root ?? document.body);
      };
      await screenFn(shot, locale);
      expect(Object.keys(seen).length).toBeGreaterThan(0);
      recorded[locale]![name] = seen;
      if (locale === "en") {
        for (const [label, h] of Object.entries(seen)) {
          expect(CJK.test(h.text), `${name} / ${label}: ${h.text}`).toBe(false);
          for (const a of h.attrs) expect(CJK.test(a), `${name} / ${label}: ${a}`).toBe(false);
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

describe("English wording of the player", () => {
  it("reads as the product's English on the lines a person meets most", async () => {
    const { container } = await loaded("en");
    const bar = harvest(container);
    expect(bar.attrs).toContain("title=Play (Space)");
    expect(bar.attrs).toContain("title=Previous subtitle (Ctrl+←)");
    expect(bar.attrs).toContain("title=Playback speed ([ ])");
    press("ArrowRight");
    expect(osd().textContent).toBe("+5 s");
    press("]");
    expect(osd().textContent).toBe("Speed 1.25×");
    press("?");
    expect((await screen.findByTestId("help")).textContent).toContain("Play or pause");
    expect(screen.getByTestId("lang-select").textContent).toBe("Traditional ChineseKorean (experimental)");
    expect(screen.getByTestId("failed-summary").textContent).toBe(
      "2 subtitles failed to translate: 1 left empty (no Korean translation), 1 shown in English instead. The model's answers failed the checks several times, for example by mixing in Japanese or having the wrong length.",
    );
    expect(screen.getByTestId("side-status").textContent).toBe("1 subtitle edited. Edits are kept when you translate again.");
  });

  it("follows the window's language when it changes", () => {
    function Switch() {
      const i18n = useI18n();
      return (
        <button type="button" data-testid="to-english" onClick={() => i18n?.setUiLanguage("en")}>
          switch
        </button>
      );
    }
    render(
      <I18nProvider initial="zh-TW">
        <Switch />
        <Player {...playerProps()} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("ctl-play").getAttribute("title")).toBe("播放 (Space)");
    click("to-english");
    expect(screen.getByTestId("ctl-play").getAttribute("title")).toBe("Play (Space)");
  });
});

afterAll(async () => {
  if (WRITE) (await files()).writeFileSync(FIXTURE, `${JSON.stringify(written, null, 1)}\n`, "utf-8");
});
