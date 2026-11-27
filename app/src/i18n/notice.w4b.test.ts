/**
 * The W4b sentences (`tests/notice_scenarios_w4b.py`): the English the backend sends, which the
 * window shows unchanged, and what a window in Traditional Chinese shows in its place.
 */
import { describe, expect, it } from "vitest";
import { parseNotices, word } from "./notice";
import type { Said } from "./said";
import fixture from "./notices.w4b.fixture.json";

interface Entry {
  readonly before: string;
  readonly text: string;
  readonly notices: unknown;
  readonly zh: string;
}

const SCENARIOS = Object.entries(fixture as unknown as Record<string, Entry>);
const sent = (entry: Entry): Said => ({ text: entry.text, notices: parseNotices(entry.notices) });

/**
 * What a Traditional Chinese sentence may still hold in English: names of products, programs, files
 * and settings, paths, and the words of other programs, as the scenarios send them. A sentence the
 * app wrote does not belong here.
 */
const DATA: readonly RegExp[] = [
  /CUDA Toolkit/g,
  /Visual C\+\+/g,
  // What a program or the operating system said, as the stand-ins in the scenarios say it.
  /ggml error no kernel image/g,
  /The system cannot find the file specified/g,
  /404 Not Found/g,
  /\[Errno 28\] No space left on device/g,
  /Expecting value: line 1 column 1 \(char 0\)/g,
  /TimeoutError: timed out/g,
  // The self-test joins its stage names as "ASR (runtime): ...; LLM (runtime): ...".
  /; LLM \(/g,
];

/** Two English words in a row, which a name alone is not and a sentence always is. */
const ENGLISH_RUN = /[A-Za-z]{2,}[,;:]? [A-Za-z]{2,}/;

describe("every W4b scenario", () => {
  it("has a notice the window keeps, with nothing dropped by the parser", () => {
    for (const [name, entry] of SCENARIOS) expect(parseNotices(entry.notices), name).toEqual(entry.notices);
  });

  it.each(SCENARIOS)("%s: English is what the backend sent before the codes", (_name, entry) => {
    expect(word(sent(entry), "en")).toBe(entry.before);
  });

  it.each(SCENARIOS)("%s: Traditional Chinese is the reviewed wording, with no English sentence left", (_name, entry) => {
    const shown = word(sent(entry), "zh-TW");
    expect(shown).toBe(entry.zh);
    expect(DATA.reduce((left, data) => left.replace(data, "◇"), shown)).not.toMatch(ENGLISH_RUN);
  });

  it.each(SCENARIOS)("%s: the other languages fill every placeholder", (_name, entry) => {
    for (const locale of ["zh-CN", "ja"] as const) {
      const shown = word(sent(entry), locale);
      expect(shown).not.toBe(entry.text);
      expect(shown).not.toMatch(/\{\w+\}/);
    }
  });
});
