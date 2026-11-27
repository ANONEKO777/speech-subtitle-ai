/**
 * The W4b part 2 sentences (`tests/notice_scenarios_w4b2.py`): the English the backend sends, which the
 * window shows unchanged, and what a window in Traditional Chinese shows in its place.
 */
import { describe, expect, it } from "vitest";
import { parseNotices, word } from "./notice";
import type { Said } from "./said";
import fixture from "./notices.w4b2.fixture.json";

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
  /Windows DPAPI/g,
  // What a program, a server or the operating system said, as the stand-ins in the scenarios say it.
  /network is down/g,
  /OSError: \[Errno 5\] I\/O error/g,
  /Server Error/g,
  /Expecting property name enclosed in double quotes: line 1 column 2 \(char 1\)/g,
];

/**
 * The sentences whose English changed on purpose (`tests/test_notices_w4b2.py` says why): "queue" where
 * the window says "batch", an API route where the window has a button, and a class name from the code.
 */
const REWORDED: Readonly<Record<string, string>> = {
  "batch.alreadyIn": "already in the batch as <item> (queued)",
  "storage.unmoved": "1 installed model(s), 0.0 GiB, stay in <tmp>/data/models and are not moved. The app now looks for models in <tmp>/elsewhere, so they show as not installed there. To move them, set the folder back, then choose \"Move existing models and switch\".",
  "move.otherContent": "<tmp>/same/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin holds other content than <tmp>/data/models/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin; left alone",
  "move.wrongSize": "<tmp>/short/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin has the wrong size after the move",
};

/** Two English words in a row, which a name alone is not and a sentence always is. */
const ENGLISH_RUN = /[A-Za-z]{2,}[,;:]? [A-Za-z]{2,}/;

describe("every W4b part 2 scenario", () => {
  it("has a notice the window keeps, with nothing dropped by the parser", () => {
    for (const [name, entry] of SCENARIOS) expect(parseNotices(entry.notices), name).toEqual(entry.notices);
  });

  it.each(SCENARIOS)("%s: English is what the backend sent before the codes", (name, entry) => {
    expect(word(sent(entry), "en")).toBe(REWORDED[name] ?? entry.before);
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
