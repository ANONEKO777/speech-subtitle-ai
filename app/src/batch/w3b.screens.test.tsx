// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LanguageInfo, LanguageSet } from "../api/client";
import type { Target } from "../api/targets";
import { CueEditor } from "../editor/CueEditor";
import { type Loaded, useCueEditing } from "../editor/useCueEditing";
import { ExportMenu } from "../export/ExportMenu";
import { exportItems } from "../export/exports";
import { I18nProvider, useI18n } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import type { Cue } from "../player/cues";
import { SummaryView } from "../summary/SummaryView";
import { AddDialog, rowsFor } from "./AddDialog";
import { BatchPanel } from "./BatchPanel";
import { CountdownModal } from "./CountdownModal";
import { EMPTY_BATCH, type Batch, type BatchItem } from "./model";
import { TargetChoice } from "./TargetChoice";

/**
 * The queue, the batch dialog, the power countdown, the cue editor, the export menu and the summary,
 * in each released language. Traditional Chinese must equal what `main` showed
 * (`w3b.screens.zh-TW.fixture.json`, written on `main` with W3B_FIXTURE=write), and English must hold
 * no Chinese, Japanese, Korean or full-width character. The stubs carry the language names the backend
 * sends (`nativeName`) and Latin text everywhere else, so a CJK character on the English render is
 * text the catalog did not carry.
 */

const mocks = vi.hoisted(() => ({ saved: null as (() => Promise<string | null>) | null }));
vi.mock("../api/backend", () => ({
  pickFolder: () => Promise.resolve(null),
  pickVideos: () => Promise.resolve([]),
  saveExport: () => mocks.saved?.() ?? Promise.resolve(null),
}));

const backend = { port: 1, token: "t" };

const NATIVE: Record<string, [string, string]> = {
  "zh-TW": ["Traditional Chinese (Taiwan)", "繁體中文（台灣）"],
  "zh-CN": ["Simplified Chinese", "简体中文"],
  en: ["English", "English"],
  ko: ["Korean", "한국어"],
  th: ["Thai", "ไทย"],
};
const info = (code: string): LanguageInfo => ({ code, name: NATIVE[code]![0], nativeName: NATIVE[code]![1], quality: code === "ko" ? "experimental" : "stable" });
const target = (code: string): Target => ({ code, name: NATIVE[code]![0], nativeName: NATIVE[code]![1], experimental: code === "ko" });
const LANGUAGES: readonly LanguageInfo[] = Object.keys(NATIVE).map(info);
const TARGETS: readonly Target[] = Object.keys(NATIVE).map(target);
const SET: LanguageSet = {
  defaultCode: "zh-TW",
  languages: [...LANGUAGES],
  unavailable: {},
  targets: { en: TARGETS, ja: TARGETS, "ja+en": [target("zh-TW")] },
};

const item = (id: string, patch: Partial<BatchItem>): BatchItem => ({
  id,
  videoPath: `C:/videos/${id}-long-talk-name.mp4`,
  projectId: id,
  lang: "zh-TW",
  sourceLang: "en",
  state: "queued",
  position: 0,
  step: null,
  progress: 0,
  etaS: null,
  attempts: 0,
  error: null,
  audioS: 600,
  ...patch,
});
const ITEMS: readonly BatchItem[] = [
  item("queued", { etaS: 1500 }),
  item("retrying", { attempts: 1, sourceLang: "ja" }),
  item("running", { state: "running", step: "translate", progress: 0.5, etaS: 600, lang: "ko", sourceLang: "ja+en" }),
  item("starting", { state: "running", lang: "th" }),
  item("paused", { state: "paused", lang: "zh-CN", progress: 0.2 }),
  item("done", { state: "done", progress: 1, lang: "en", sourceLang: "ja" }),
  item("failed", { state: "failed", error: "CUDA error: out of memory. See https://example.com/help" }),
  item("cancelled", { state: "cancelled" }),
];
const loadedBatch = (patch: Partial<Batch>): Batch => ({ ...EMPTY_BATCH, loaded: true, link: "live", ...patch });

const CUES: readonly Cue[] = [
  { id: 1, startMs: 1000, endMs: 2000, src: "Hello there.", lang: "en", zh: "Hi." },
  { id: 2, startMs: 3000, endMs: 4000, src: "Second one.", lang: "en", zh: "Two." },
  { id: 3, startMs: 5000, endMs: 6000, src: "Third one.", lang: "en", zh: "Three." },
];
const LOADED: Loaded = { cues: CUES, editedIds: [] };

function Editing({ id }: { readonly id: number }) {
  const editing = useCueEditing(backend, "p", "zh-TW", LOADED);
  const cue = editing.state.cues.find((c) => c.id === id)!;
  return (
    <div>
      <button type="button" data-testid="begin" onClick={() => editing.begin(id)} />
      <button type="button" data-testid="undo-now" onClick={() => void editing.undo()} />
      <p data-testid="failure">{editing.failure}</p>
      {editing.editingId === id && (
        <CueEditor
          cue={cue}
          marks={false}
          hooks={{
            validate: (d) => editing.validate(id, d),
            refusal: editing.refusal,
            onCommit: (d) => editing.commit(id, d),
            onCancel: editing.cancel,
          }}
        />
      )}
    </div>
  );
}

function Exporting({ label }: { readonly label: string }) {
  const [result, setResult] = useState("");
  return (
    <div>
      <ExportMenu backend={backend} projectId="p" items={exportItems("C:/videos/talk.mp4", "zh-TW", label, "ja")} onResult={setResult} />
      <p data-testid="export-result">{result}</p>
    </div>
  );
}

const SUMMARY = [
  "# A talk about compilers",
  "> The speaker argues that parsers are easy.",
  "## Chapters",
  "- [00:12](#t=12) Opening",
  "- [1:05:30](#t=3930) **Closing** remarks",
  "A plain paragraph.",
].join("\n\n");

type Reply = { status: number; body: unknown } | Error;
let replies: Record<string, Reply> = {};
function stubBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const key = `${init?.method ?? "GET"} ${path}`;
      const reply = replies[key] ?? Object.entries(replies).find(([k]) => key.startsWith(k))?.[1] ?? { status: 200, body: {} };
      if (reply instanceof Error) return Promise.reject(reply);
      const body = typeof reply.body === "string" ? reply.body : JSON.stringify(reply.body);
      return Promise.resolve(new Response(body, { status: reply.status, statusText: "Problem" }));
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
const FIXTURE = "src/batch/w3b.screens.zh-TW.fixture.json";
const WRITE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["W3B_FIXTURE"] === "write";
interface Files {
  readFileSync: (path: string, encoding: string) => string;
  writeFileSync: (path: string, data: string, encoding: string) => void;
}
const files = async () => (await import("node:fs" as string)) as Files;
const written: Record<string, Record<string, Harvest>> = {};

const wrap = (locale: Locale, node: ReactNode) => <I18nProvider initial={locale}>{node}</I18nProvider>;
const panel = (locale: Locale, batch: Batch) =>
  render(wrap(locale, <BatchPanel backend={backend} batch={batch} languages={LANGUAGES} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />));
const change = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });
const NOW = 1_800_000_000_000;

type Shot = (name: string, root?: Element) => void;
type Screen = (shot: Shot, locale: Locale) => Promise<void>;

const SCREENS: Record<string, Screen> = {
  "the queue, empty": async (shot, locale) => {
    const { container } = panel(locale, loadedBatch({}));
    shot("empty", container);
  },
  "the queue with an item in every state": async (shot, locale) => {
    const { container } = panel(locale, loadedBatch({ items: ITEMS }));
    shot("list", container);
  },
  "the queue before the first estimate": async (shot, locale) => {
    const { container } = panel(locale, loadedBatch({ items: [item("one", { state: "running", step: "audio", progress: 0.05 })] }));
    shot("no estimate", container.querySelector("[data-testid='batch-summary']") as Element);
  },
  "the queue paused and reconnecting": async (shot, locale) => {
    const { container } = panel(locale, loadedBatch({ items: ITEMS.slice(0, 2), paused: true, link: "lost" }));
    shot("paused", container);
  },
  "the queue set to sleep or shut down": async (shot, locale) => {
    for (const onDone of ["sleep", "shutdown"] as const) {
      const { container, unmount } = panel(locale, loadedBatch({ settings: { onDone, allowPower: true } }));
      shot(`armed ${onDone}`, container.querySelector("[data-testid='ondone']") as Element);
      unmount();
    }
  },
  "the consent to sleep or shut down": async (shot, locale) => {
    for (const onDone of ["sleep", "shutdown"] as const) {
      const { container, unmount } = panel(locale, loadedBatch({}));
      change("ondone-select", onDone);
      fireEvent.click(screen.getByTestId("ondone-agree"));
      shot(`consent ${onDone}`, container.querySelector("[data-testid='ondone']") as Element);
      unmount();
    }
  },
  "the countdown before sleep or shutdown": async (shot, locale) => {
    vi.spyOn(Date, "now").mockReturnValue(NOW);
    for (const action of ["sleep", "shutdown"] as const) {
      const { container, unmount } = render(wrap(locale, <CountdownModal countdown={{ action, deadlineMs: NOW + 42_000 }} onCancel={() => undefined} />));
      shot(`countdown ${action}`, container);
      unmount();
    }
  },
  "the batch dialog, empty": async (shot, locale) => {
    const { container } = render(wrap(locale, <AddDialog backend={backend} languages={SET} initial={[]} onClose={() => undefined} onAdded={() => undefined} />));
    shot("empty", container);
  },
  "the batch dialog with several files, a folder and the language guesses": async (shot, locale) => {
    replies["POST /api/languages/detect"] = { status: 200, body: { detected: "ja", suggested: "en", mixed_unavailable: null, confidence: 0.9, sure: true, shares: { ja: 0.9, en: 0.1 }, clear: 20, samples: [] } };
    const initial = rowsFor(["C:/videos/first-talk.mp4", "C:/videos/second-talk.mkv", "C:/videos/a folder"], ["zh-TW", "ko"], "ja");
    const { container } = render(wrap(locale, <AddDialog backend={backend} languages={SET} initial={initial} onClose={() => undefined} onAdded={() => undefined} />));
    shot("detecting", container);
    await waitFor(() => expect(screen.getAllByTestId("add-row-detect").every((n) => n.getAttribute("data-state") === "done")).toBe(true));
    shot("guessed", container);
    fireEvent.click(screen.getAllByTestId("add-row-lang")[0]!);
    shot("target list", screen.getByTestId("add-row-lang-list"));
  },
  "the batch dialog after the backend skipped or refused": async (shot, locale) => {
    replies["POST /api/queue/items"] = { status: 201, body: { added: [{ id: "x" }], skipped: [{ path: "C:/videos/broken.mp4", reason: "Not a video file" }] } };
    const initial = rowsFor(["C:/videos/broken.mp4"], ["zh-TW"], "en");
    const { container, unmount } = render(wrap(locale, <AddDialog backend={backend} languages={SET} initial={initial} onClose={() => undefined} onAdded={() => undefined} />));
    fireEvent.click(screen.getByTestId("add-submit"));
    await screen.findByTestId("add-skipped");
    shot("skipped", container);
    unmount();
    replies["POST /api/queue/items"] = { status: 500, body: { detail: "The disk is full" } };
    const again = render(wrap(locale, <AddDialog backend={backend} languages={SET} initial={initial} onClose={() => undefined} onAdded={() => undefined} />));
    fireEvent.click(screen.getByTestId("add-submit"));
    await screen.findByTestId("add-error");
    shot("refused", again.container);
  },
  "the subtitle language choice": async (shot, locale) => {
    const { container } = render(wrap(locale, <TargetChoice targets={TARGETS} value={["zh-TW", "ko", "th"]} onChange={() => undefined} label="x" testid="pick" />));
    fireEvent.click(screen.getByTestId("pick"));
    shot("open", container);
  },
  "the cue editor and each refusal": async (shot, locale) => {
    const { container } = render(wrap(locale, <Editing id={2} />));
    fireEvent.click(screen.getByTestId("begin"));
    const editor = () => container.querySelector("[data-testid='cue-editor']") as Element;
    shot("editing", editor());
    const tries: ReadonlyArray<readonly [string, string, string, string]> = [
      ["bad time", "abc", "0:04.000", "Two."],
      ["empty", "0:03.000", "0:04.000", ""],
      ["end before start", "0:03.500", "0:03.200", "Two."],
      ["too long", "0:03.000", "0:10.500", "Two."],
      ["out of order", "0:00.500", "0:00.900", "Two."],
      ["overlaps the one before", "0:01.500", "0:02.500", "Two."],
      ["overlaps the one after", "0:03.000", "0:05.500", "Two."],
    ];
    for (const [name, start, end, text] of tries) {
      change("edit-start", start);
      change("edit-end", end);
      change("edit-text", text);
      shot(name, screen.getByTestId("edit-error"));
    }
    change("edit-start", "0:03.000");
    change("edit-end", "0:04.000");
    change("edit-text", "Two.");
    fireEvent.keyDown(screen.getByTestId("edit-source"), { key: "a" });
    shot("source locked", screen.getByTestId("edit-error"));
  },
  "the cue editor when the backend refuses": async (shot, locale) => {
    const cases: ReadonlyArray<readonly [string, Reply]> = [
      ["a problem code", { status: 422, body: { detail: { problems: [{ id: 2, code: "bad_text", message: "extra spaces" }] } } }],
      ["a busy project", { status: 409, body: { detail: "A job is running" } }],
      ["no backend", new Error("connection refused")],
    ];
    for (const [name, reply] of cases) {
      replies = { "PUT /api/projects/p/subtitles": reply };
      const { unmount } = render(wrap(locale, <Editing id={2} />));
      fireEvent.click(screen.getByTestId("begin"));
      change("edit-text", "Two, changed.");
      fireEvent.keyDown(screen.getByTestId("edit-text"), { key: "Enter" });
      shot(name, await screen.findByTestId("edit-error"));
      unmount();
    }
  },
  "the undo that the backend refuses": async (shot, locale) => {
    replies = { "GET /api/projects/p/edits": { status: 200, body: { ids: [2] } } };
    const { unmount } = render(wrap(locale, <Editing id={2} />));
    fireEvent.click(screen.getByTestId("begin"));
    change("edit-text", "Two, changed.");
    fireEvent.keyDown(screen.getByTestId("edit-text"), { key: "Enter" });
    await waitFor(() => expect(screen.queryByTestId("cue-editor")).toBeNull());
    replies["PUT /api/projects/p/subtitles"] = new Error("connection refused");
    fireEvent.click(screen.getByTestId("undo-now"));
    await waitFor(() => expect(screen.getByTestId("failure").textContent).not.toBe(""));
    shot("failure", screen.getByTestId("failure"));
    unmount();
  },
  "the export menu and what each entry reports": async (shot, locale) => {
    const { container } = render(wrap(locale, <Exporting label={locale === "en" ? "Traditional Chinese" : "繁體中文"} />));
    shot("closed", container);
    fireEvent.click(screen.getByTestId("export-menu"));
    shot("open", container);
    replies = { "GET /api/projects/p/subtitles": { status: 200, body: "1\n00:00:01,000 --> 00:00:02,000\nHi.\n" } };
    const outcomes: ReadonlyArray<readonly [string, string, () => Promise<string | null>]> = [
      ["saved", "srt-zh", () => Promise.resolve("C:/out/talk.zh-TW.srt")],
      ["cancelled", "srt-bilingual", () => Promise.resolve(null)],
      ["failed", "vtt", () => Promise.reject(new Error("Access denied"))],
    ];
    for (const [name, id, saved] of outcomes) {
      mocks.saved = saved;
      if (!screen.queryByTestId("export-list")) fireEvent.click(screen.getByTestId("export-menu"));
      fireEvent.click(screen.getByTestId(`export-${id}`));
      await waitFor(() => expect(screen.getByTestId("export-menu").hasAttribute("disabled")).toBe(false));
      shot(name, screen.getByTestId("export-result"));
    }
    replies = { "GET /api/projects/p/summary": { status: 409, body: { detail: "no summary" } } };
    fireEvent.click(screen.getByTestId("export-menu"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("export-summary"));
    });
    await waitFor(() => expect(screen.getByTestId("export-result").textContent).not.toContain("talk.zh-TW.srt"));
    await waitFor(() => expect(screen.getByTestId("export-menu").hasAttribute("disabled")).toBe(false));
    shot("no summary", screen.getByTestId("export-result"));
  },
  "the summary and its empty state": async (shot, locale) => {
    const full = render(wrap(locale, <SummaryView markdown={SUMMARY} onSeek={() => undefined} />));
    shot("summary", full.container);
    full.unmount();
    const empty = render(wrap(locale, <SummaryView markdown={null} onSeek={() => undefined} />));
    shot("empty", empty.container);
  },
};

beforeEach(() => {
  localStorage.clear();
  replies = {};
  mocks.saved = null;
  stubBackend();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe.each(["zh-TW", "en"] as const)("W3b screens in %s", (locale) => {
  for (const [name, screenFn] of Object.entries(SCREENS)) {
    it(name, async () => {
      const seen: Record<string, Harvest> = {};
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
  it("names each state, step and language of the batch in English", () => {
    panel("en", loadedBatch({ items: ITEMS }));
    const state = (id: string) => screen.getByTestId(`qstate-${id}`).textContent;
    expect(["queued", "running", "paused", "done", "failed", "cancelled"].map(state)).toEqual(["Waiting", "Processing", "Paused", "Done", "Failed", "Cancelled"]);
    expect(screen.getByTestId("qstep-running").textContent).toBe("Translating (5/7)");
    expect(screen.getByTestId("qstep-retrying").textContent).toBe("Waiting to resume");
    expect(screen.getByTestId("qlang-running").textContent).toBe("Japanese + EnglishKoreanExperimental");
    expect(screen.getByTestId("qlang-paused").textContent).toBe("Simplified Chinese");
    expect(screen.getByTestId("batch-summary").textContent).toBe("2/7processedabout 25 min left");
  });

  it("keeps the meaning of the sleep and shutdown consent", () => {
    panel("en", loadedBatch({}));
    change("ondone-select", "shutdown");
    expect(screen.getByTestId("ondone-warn").textContent).toBe(
      "Shutting down interrupts everything else running on the computer. When the batch finishes, the computer first counts down 60 seconds, and you can press Cancel to stop it. If you don't, it shuts down, and any unsaved work is lost.I understand, and I agree to shut down the computer when the batch finishesCancelTurn on",
    );
    expect(screen.getByTestId("ondone-confirm").hasAttribute("disabled")).toBe(true);
  });

  it("counts the seconds before sleep with the right plural", () => {
    vi.spyOn(Date, "now").mockReturnValue(NOW);
    const { rerender } = render(wrap("en", <CountdownModal countdown={{ action: "sleep", deadlineMs: NOW + 1000 }} onCancel={() => undefined} />));
    expect(screen.getByTestId("countdown").querySelector("p")?.textContent).toBe("The computer will go to sleep in 1 second.");
    rerender(wrap("en", <CountdownModal countdown={{ action: "shutdown", deadlineMs: NOW + 60_000 }} onCancel={() => undefined} />));
    expect(screen.getByTestId("countdown").querySelector("p")?.textContent).toBe("The computer will shut down in 60 seconds.");
    expect(screen.getByTestId("countdown-cancel").textContent).toBe("Cancel, don't shut down");
  });

  it("labels the export menu with short English entries and keeps the format and file names", () => {
    render(wrap("en", <Exporting label="Traditional Chinese" />));
    fireEvent.click(screen.getByTestId("export-menu"));
    expect([...screen.getByTestId("export-list").querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "SRT (original)",
      "SRT (Traditional Chinese)",
      "SRT (bilingual)",
      "ASS (bilingual)",
      "VTT (bilingual)",
      "Summary (summary.md)",
    ]);
  });

  it("explains a refused cue edit in English", () => {
    const { container } = render(wrap("en", <Editing id={2} />));
    fireEvent.click(screen.getByTestId("begin"));
    change("edit-start", "0:03.000");
    change("edit-end", "0:05.500");
    expect(screen.getByTestId("edit-error").textContent).toBe("Overlaps the next subtitle, which starts at 0:05.000");
    expect(container.querySelector(".editor-hint")?.textContent).toBe("Enter to save · Shift+Enter for a new line · Esc to cancel");
  });
});

describe("switching the window language", () => {
  function Switcher({ children }: { readonly children: ReactNode }) {
    const i18n = useI18n();
    return (
      <>
        <button type="button" data-testid="to-en" onClick={() => i18n?.setUiLanguage("en")} />
        {children}
      </>
    );
  }

  it("redraws the batch, the editor's refusal and the summary at once", () => {
    render(
      <I18nProvider initial="zh-TW">
        <Switcher>
          <BatchPanel backend={backend} batch={loadedBatch({ items: ITEMS.slice(2, 3) })} languages={LANGUAGES} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />
          <Editing id={2} />
          <SummaryView markdown={null} onSeek={() => undefined} />
        </Switcher>
      </I18nProvider>,
    );
    fireEvent.click(screen.getByTestId("begin"));
    change("edit-text", "");
    expect(screen.getByTestId("qstate-running").textContent).toBe("處理中");
    expect(screen.getByTestId("edit-error").textContent).toBe("文字不能是空的");
    fireEvent.click(screen.getByTestId("to-en"));
    expect(screen.getByTestId("qstate-running").textContent).toBe("Processing");
    expect(screen.getByTestId("edit-error").textContent).toBe("The text can't be empty");
    expect(screen.getByTestId("summary-empty").textContent).toBe("No summary for this language yet.");
  });
});
