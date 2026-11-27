import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { parseSelfTest } from "../manage/parse";
import { t } from ".";
import { CATALOGS } from "./catalog";
import type { Locale } from "./locale";
import { NOT_ENGLISH } from "./notEnglish";
import { type Notice, SENT, type Said, parseNotices, said, word, wordNotice } from "./notice";
import shellBefore from "./notices.shell.before.json";
import shell from "./notices.shell.json";
import fixture from "./notices.wire.fixture.json";

const LOCALES = Object.keys(CATALOGS) as Locale[];
const catalog = (locale: Locale): Readonly<Record<string, string>> => CATALOGS[locale];
const names = (template: string) => [...new Set([...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]!))].sort();

describe("every code a sender has", () => {
  it("has a catalog entry in all four languages, with the sender's placeholders", () => {
    expect(LOCALES).toHaveLength(4);
    const problems = Object.entries(SENT).flatMap(([code, sent]) =>
      LOCALES.flatMap((locale) => {
        const entry = catalog(locale)[`notice.${code}`];
        if (entry === undefined) return [`${locale}: notice.${code} is missing`];
        const wanted = Object.keys(sent.params).sort();
        return names(entry).join() === wanted.join() ? [] : [`${locale}: notice.${code} has {${names(entry)}}, the sender sends {${wanted}}`];
      }),
    );
    expect(problems).toEqual([]);
  });

  it("says in English exactly what the sender's template says", () => {
    for (const [code, sent] of Object.entries(SENT)) expect(catalog("en")[`notice.${code}`], code).toBe(sent.english);
  });

  it("uses only the parameter kinds the window can word", () => {
    for (const sent of Object.values(SENT)) {
      for (const kind of Object.values(sent.params)) expect(["text", "list", "clauses", "language"]).toContain(kind);
    }
  });

  it("is the only thing under notice. in the catalog", () => {
    const orphans = Object.keys(catalog("en")).filter((key) => key.startsWith("notice.") && !(key.slice("notice.".length) in SENT));
    expect(orphans).toEqual([]);
  });
});

/** What `tests/notice_scenarios.py` got from the backend now, and the text of the same call before. */
const WIRE = Object.entries(fixture as unknown as Record<string, { before: string; text: string; notices: unknown }>);
const sent = (entry: { text: string; notices: unknown }): Said => ({ text: entry.text, notices: parseNotices(entry.notices) });
/** The sentences that were Chinese before the codes. A later round gave codes to English ones around them (`notice.w4b.test.ts`). */
const WAS_CHINESE = /^(runtime|fonts|render|platform|secrets)\./;
const chineseOnly = (said: Said): Said => ({ text: said.text, notices: said.notices.filter((n) => WAS_CHINESE.test(n.code)) });

/** Parameter values that are the video's own words or characters, which English shows as they are. */
const DATA = new Set(["chars"]);
const withoutData = (text: string, notices: readonly Notice[]) =>
  notices.reduce((left, n) => Object.entries(n.params).reduce((l, [name, v]) => (DATA.has(name) ? l.replaceAll(String(v), "") : l), left), text);

describe("every backend scenario", () => {
  it("has a notice the window keeps, with nothing dropped by the parser", () => {
    expect(WIRE).toHaveLength(20);
    for (const [name, entry] of WIRE) expect(parseNotices(entry.notices), name).toEqual(entry.notices);
  });

  it.each(WIRE)("%s: Traditional Chinese is what the backend said before, character for character", (_name, entry) => {
    expect(word(chineseOnly(sent(entry)), "zh-TW")).toBe(entry.before);
  });

  it.each(WIRE)("%s: English is the backend's own text and holds no other script", (_name, entry) => {
    const shown = word(sent(entry), "en");
    expect(shown).toBe(entry.text);
    expect(withoutData(shown, parseNotices(entry.notices))).not.toMatch(NOT_ENGLISH);
  });

  it.each(WIRE)("%s: the other languages fill every placeholder", (_name, entry) => {
    for (const locale of ["zh-CN", "ja"] as const) {
      const shown = word(sent(entry), locale);
      expect(shown).not.toBe(entry.text);
      expect(shown).not.toMatch(/\{\w+\}/);
    }
  });
});

const SHELL_VALUES: Readonly<Record<string, string>> = {
  error: "The system cannot find the file specified. (os error 2)",
  detail: "Traceback (most recent call last):\r\nValueError: boom\r\n",
};
const fill = (template: string) => template.replace(/\{(\w+)\}/g, (_, name: string) => SHELL_VALUES[name]!);

/** A shell text as `notice.rs` makes it: the template filled, and itself as the one notice. */
function fromShell(code: keyof typeof shell): Said {
  const { english, params } = shell[code];
  const message = fill(english);
  return { text: message, notices: [{ code, message, params: Object.fromEntries(Object.keys(params).map((n) => [n, SHELL_VALUES[n]!])) }] };
}

const SHELL_CODES = Object.keys(shell) as (keyof typeof shell)[];

describe("every shell sentence", () => {
  it("replaced one old sentence each, and the file filter is the only one besides them", () => {
    expect(Object.keys(shellBefore).sort()).toEqual([...SHELL_CODES, "shell.mediaFilter"].sort());
    expect(t("zh-TW", "shell.mediaFilter")).toBe(shellBefore["shell.mediaFilter"]);
    expect(t("en", "shell.mediaFilter")).not.toMatch(NOT_ENGLISH);
  });

  it.each(SHELL_CODES)("%s: Traditional Chinese is what the shell said before, and English holds no other script", (code) => {
    expect(word(fromShell(code), "zh-TW")).toBe(fill(shellBefore[code]));
    expect(word(fromShell(code), "en")).toBe(fromShell(code).text);
    expect(word(fromShell(code), "en")).not.toMatch(NOT_ENGLISH);
  });

  it("words the backend's own sentence inside the output of a backend that stopped early", () => {
    const platform = (fixture as unknown as Record<string, { before: string; text: string; notices: Notice[] }>)["platform.linux"]!;
    const detail = `error: ${platform.text}\r\n`;
    const message = shell["shell.backend.exitedEarly"].english.replace("{detail}", () => detail);
    const early: Said = {
      text: message,
      notices: [{ code: "shell.backend.exitedEarly", message, params: { detail } }, ...platform.notices],
    };

    expect(word(early, "zh-TW")).toBe(`後端在就緒前就結束了。\nerror: ${platform.before}\r\n`);
    expect(word(early, "en")).toBe(message);
  });
});

const KNOWN: Notice = { code: "runtime.vcMissing", message: "Get it from X.", params: { url: "X" } };

describe("a notice the window cannot word", () => {
  it.each<[string, Notice]>([
    ["an unknown code", { ...KNOWN, code: "runtime.fromANewerBackend" }],
    ["a code that is an object's own name", { ...KNOWN, code: "constructor" }],
    ["a missing parameter", { ...KNOWN, params: {} }],
    ["a parameter of another kind", { ...KNOWN, params: { url: ["X"] } }],
    ["a list sent as text", { code: "fonts.noJapaneseMac", message: "No font.", params: { fonts: "Hiragino" } }],
  ])("shows its English message for %s, in every language", (_what, notice) => {
    for (const locale of LOCALES) expect(wordNotice(notice, locale)).toBe(notice.message);
  });

  it("shows a text with no notices as it came, such as one an earlier version stored", () => {
    const old = "EngineUnavailableError: 這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64）。";
    for (const locale of LOCALES) expect(word({ text: old, notices: [] }, locale)).toBe(old);
  });
});

describe("wording a text", () => {
  it("replaces every copy of a notice, and leaves a $ in a parameter as it is", () => {
    const notice: Notice = { ...KNOWN, message: "Get $& and $1.", params: { url: "$&" } };
    const text = `a: ${notice.message}; b: ${notice.message}.`;

    expect(word({ text, notices: [notice] }, "zh-TW")).toBe(`a: ${wordNotice(notice, "zh-TW")}; b: ${wordNotice(notice, "zh-TW")}.`);
    expect(wordNotice(notice, "zh-TW")).toContain("請到 $& 下載");
  });

  it("names a language parameter and joins a list the way each language does", () => {
    const notice: Notice = { code: "fonts.noTargetFont", message: "m", params: { language: "ko", fonts: ["A", "B"] } };

    expect(wordNotice(notice, "en")).toContain("Korean subtitles (tried A, B)");
    expect(wordNotice(notice, "zh-TW")).toContain("한국어字幕的字型（試過 A、B）");
    expect(wordNotice(notice, "ja")).toContain("韓国語");
  });
});

describe("what a failure said", () => {
  it("reads an ApiError, the shell's rejection, an Error and a string", () => {
    expect(said(new ApiError(422, "Get it from X.", [], null, [KNOWN]))).toEqual({ text: "Get it from X.", notices: [KNOWN] });
    expect(said({ message: "Get it from X.", notices: [KNOWN] })).toEqual({ text: "Get it from X.", notices: [KNOWN] });
    expect(said(new Error("boom"))).toEqual({ text: "boom", notices: [] });
    expect(said("denied")).toEqual({ text: "denied", notices: [] });
  });

  it("leaves out anything that is not a notice", () => {
    expect(parseNotices([KNOWN, null, 1, { code: "a" }, { ...KNOWN, message: "" }, { ...KNOWN, params: { url: 1 } }])).toEqual([KNOWN]);
    expect(parseNotices("x")).toEqual([]);
  });

  it("reads the notices of a self-test beside each of its three texts", () => {
    const notices = [KNOWN];
    const parsed = parseSelfTest({
      ok: false,
      stages: [{ detail: KNOWN.message, detail_notices: notices }],
      fallback: { reason: KNOWN.message, reason_notices: notices },
      message: KNOWN.message,
      message_notices: notices,
    });
    const wanted = { text: KNOWN.message, notices };

    expect([parsed?.message, parsed?.fallback?.reason, parsed?.stages[0]?.detail]).toEqual([wanted, wanted, wanted]);
  });
});
