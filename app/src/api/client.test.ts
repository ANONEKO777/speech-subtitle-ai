import { afterEach, describe, expect, it, vi } from "vitest";
import { tZhTW } from "../i18n";
import { fetchCues, fetchLanguageSet, fetchProject, putCues, startJob } from "./client";

const backend = { port: 1, token: "t" };

const answer = (body: unknown) => vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status: 200 })));

afterEach(() => vi.unstubAllGlobals());

describe("fetchCues", () => {
  it("reads src and lang of a Japanese cue and ignores the temporary en alias", async () => {
    vi.stubGlobal(
      "fetch",
      answer({ cues: [{ id: 0, start_ms: 0, end_ms: 900, src: "こんにちは", lang: "ja", zh: "你好", en: "ALIAS" }] }),
    );
    expect(await fetchCues(backend, "p", "zh-TW")).toEqual([
      { id: 0, startMs: 0, endMs: 900, src: "こんにちは", lang: "ja", zh: "你好" },
    ]);
  });

  it("reads the en key of an English cue, which has no lang", async () => {
    vi.stubGlobal("fetch", answer({ cues: [{ id: 3, start_ms: 10, end_ms: 20, en: "Hello", zh: "哈囉" }] }));
    expect(await fetchCues(backend, "p", "zh-TW")).toEqual([
      { id: 3, startMs: 10, endMs: 20, src: "Hello", lang: "en", zh: "哈囉" },
    ]);
  });

  it("refuses a Japanese cue that has src but no lang", async () => {
    vi.stubGlobal("fetch", answer({ cues: [{ id: 0, start_ms: 0, end_ms: 9, src: "あ", zh: "啊" }] }));
    await expect(fetchCues(backend, "p", "zh-TW")).rejects.toThrow("unexpected cue");
  });

  it("does not need the alias: a Japanese cue without en still reads", async () => {
    vi.stubGlobal("fetch", answer({ cues: [{ id: 0, start_ms: 0, end_ms: 9, src: "あ", lang: "ja", zh: "啊" }] }));
    expect((await fetchCues(backend, "p", "zh-TW"))[0]?.src).toBe("あ");
  });
});

describe("fetchCues in a mixed talk", () => {
  it("keeps the language of each cue, so neighbours of different languages stay apart", async () => {
    vi.stubGlobal(
      "fetch",
      answer({
        cues: [
          { id: 0, start_ms: 0, end_ms: 900, src: "こんにちは", lang: "ja", zh: "你好" },
          { id: 1, start_ms: 900, end_ms: 2000, src: "Thank you", lang: "en", zh: "謝謝" },
        ],
      }),
    );
    const cues = await fetchCues(backend, "p", "zh-TW");
    expect(cues.map((c) => c.lang)).toEqual(["ja", "en"]);
  });
});

describe("fetchLanguageSet", () => {
  const set = (sources: unknown) =>
    answer({
      default: "zh-TW",
      languages: [{ code: "zh-TW", name: "Traditional Chinese", native_name: "繁體中文", quality: "stable" }],
      sources,
    });

  it("lists the video languages this machine cannot process, with the reason in words", async () => {
    vi.stubGlobal(
      "fetch",
      set([
        { code: "en", available: true, reason: null },
        { code: "ja", available: true, reason: null },
        { code: "ja+en", available: false, reason: "missing_files" },
      ]),
    );
    expect((await fetchLanguageSet(backend)).unavailable).toEqual({ "ja+en": "這台電腦沒有安裝混合語言所需的模型" });
  });

  it("offers everything when the backend does not say, so its own refusal is what a person sees", async () => {
    vi.stubGlobal("fetch", set(undefined));
    expect((await fetchLanguageSet(backend)).unavailable).toEqual({});
  });
});

describe("putCues", () => {
  it("sends the source text under the key the backend expects", async () => {
    const fetchImpl = answer({});
    vi.stubGlobal("fetch", fetchImpl);
    await putCues(backend, "p", "zh-TW", [{ id: 0, startMs: 0, endMs: 9, src: "あ", lang: "ja", zh: "啊" }]);
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ cues: [{ id: 0, start_ms: 0, end_ms: 9, en: "あ", zh: "啊" }] });
  });
});

describe("startJob", () => {
  it("sends the video language in the job body", async () => {
    const fetchImpl = answer({ id: "j1" });
    vi.stubGlobal("fetch", fetchImpl);
    expect(await startJob(backend, "p", "ja")).toBe("j1");
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ source_lang: "ja" });
  });

  it("says English when no language is given", async () => {
    const fetchImpl = answer({ id: "j2" });
    vi.stubGlobal("fetch", fetchImpl);
    await startJob(backend, "p");
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ source_lang: "en" });
  });
});

describe("startJob with a target language", () => {
  it("sends the target next to the video language, and nothing about a target when none is asked", async () => {
    const fetchImpl = answer({ id: "j3" });
    vi.stubGlobal("fetch", fetchImpl);
    await startJob(backend, "p", "ja", "ko");
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ source_lang: "ja", target_lang: "ko" });
  });
});

describe("a job refused because one already runs", () => {
  it("says so in the window's language, with no job id and no English", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "job bb44ca76c6ee4186 is already running on this project" }), { status: 409 }))),
    );
    const error = await startJob(backend, "p", "ja", "ko").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 409, message: tZhTW("errors.jobRunning") });
    expect(tZhTW("errors.jobRunning")).not.toMatch(/[A-Za-z0-9]/);
  });

  it("leaves other refusals as the backend wrote them", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "the video is gone: x" }), { status: 422 }))));
    await expect(startJob(backend, "p")).rejects.toThrow("the video is gone: x");
  });
});

describe("the targets a video language has", () => {
  it("are read from the sources of the languages reply, with the experimental flag", async () => {
    vi.stubGlobal(
      "fetch",
      answer({
        default: "zh-TW",
        languages: [],
        sources: [{ code: "ja", available: true, reason: null, targets: [{ code: "ko", name: "Korean", native_name: "한국어", experimental: true }] }],
      }),
    );
    expect((await fetchLanguageSet(backend)).targets).toEqual({
      ja: [{ code: "ko", name: "Korean", nativeName: "한국어", experimental: true }],
    });
  });
});

describe("fetchProject and the cues a translation could not do", () => {
  const project = (extra: object) =>
    answer({ id: "p", video_path: "D:/a.mp4", steps: {}, languages: {}, active_job: null, source_lang: "ja", ...extra });

  it("reads the failed and the English cues of each language that has any", async () => {
    vi.stubGlobal("fetch", project({ failed_cues: { ko: { failed: [3, 5], english: [5] }, en: { failed: [], english: [] }, bad: 7 } }));
    expect((await fetchProject(backend, "p")).failedCues).toEqual({ ko: { failed: [3, 5], english: [5] } });
  });

  it("reads none from a project of an older backend", async () => {
    vi.stubGlobal("fetch", project({}));
    expect((await fetchProject(backend, "p")).failedCues).toEqual({});
  });
});
