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
  /moov atom not found/g,
  /Invalid data/g,
  /file does not start with RIFF id/g,
  /\[Errno 2\] No such file or directory: 'absent\.json'/g,
  /Expecting property name enclosed in double quotes: line 1 column 2 \(char 1\)/g,
  /out of memory/g,
  /Access is denied/g,
  /Internal Server Error/g,
  /Service Unavailable/g,
  // A command to type, as it is.
  /`brew install ffmpeg`/g,
  /model crashed/g,
  /connection refused/g,
  // NOT another program's words: the app wrote these two kinds in English and they are quoted as
  // a detail. The first two are what the check of a model's answer tells the model, and the third
  // is what the reader of a damaged subtitle file says. See docs/i18n-notes/w4b1.md.
  /the reply is not valid JSON/g,
  /the topic is empty/g,
  /subs file: invalid JSON/g,
  // And what the store of the API key says, quoted as the detail of a saved key that cannot be read.
  /Windows DPAPI failed/g,
];

/**
 * The sentences whose English changed: one said "queue" where the window says "batch", a runtime
 * row was told to verify, which only a model row can, and a program that exited with no output
 * left a colon with nothing after it.
 */
const REWORDED: Readonly<Record<string, string>> = {
  "selftest.exitsSilently.message":
    "Self-test failed: ASR (whispercpp-b5454-win-cpu): program.exe exited with code 3: no output; LLM (llama.cpp-b12068-win-cpu): program.exe exited with code 3: no output.",
  "selftest.exitsSilently.stage0": "program.exe exited with code 3: no output",
  "selftest.exitsSilently.stage1": "program.exe exited with code 3: no output",
  "batch.crashed": "the batch crashed",
  "updates.item.runtimeUnrecorded": "installed, but its version was not recorded; re-download it to compare with registry version b5454",
  "updates.item.runtimeCheckFailed": "installed, but its last check failed; re-download it to compare with registry version b5454",
};

/** Two English words in a row, which a name alone is not and a sentence always is. */
const ENGLISH_RUN = /[A-Za-z]{2,}[,;:]? [A-Za-z]{2,}/;

describe("every W4b scenario", () => {
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

  it.each(SCENARIOS.filter(([name]) => name.startsWith("selftest.")))(
    "%s: Traditional Chinese joins the self-test's failures with Chinese punctuation, and no colon dangles",
    (_name, entry) => {
      expect(word(sent(entry), "zh-TW")).not.toMatch(/[:;] |：[；;）)]|：$/);
    },
  );

  it.each(SCENARIOS)("%s: the other languages fill every placeholder", (_name, entry) => {
    for (const locale of ["zh-CN", "ja"] as const) {
      const shown = word(sent(entry), locale);
      expect(shown).not.toBe(entry.text);
      expect(shown).not.toMatch(/\{\w+\}/);
    }
  });
});
