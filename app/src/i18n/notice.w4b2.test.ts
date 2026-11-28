/**
 * The W4b part 2 sentences (`tests/notice_scenarios_w4b2.py`): the English the backend sends, which the
 * window shows unchanged, and what a window in Traditional Chinese shows in its place.
 */
import { describe, expect, it } from "vitest";
import { parseNotices, word } from "./notice";
import type { Said } from "./said";
import fixture from "./notices.w4b2.fixture.json";
import { parseMove } from "../manage/parse";
import shellBefore from "./notices.shell.before.json";
import shell from "./notices.shell.json";

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
 * the window says "batch", an API route where the window has a button, a class name from the code, and
 * a sentence that said "unknown memory of memory", and a language named by its code.
 */
const REWORDED: Readonly<Record<string, string>> = {
  "batch.alreadyIn": "already in the batch as <item> (queued)",
  "storage.unmoved": "1 installed model(s), 0.0 GiB, stay in <tmp>/data/models and are not moved. The app now looks for models in <tmp>/elsewhere, so they show as not installed there. To move them, set the folder back, then choose \"Move existing models and switch\".",
  "move.otherContent": "<tmp>/same/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin holds other content than <tmp>/data/models/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin; left alone",
  "move.wrongSize": "<tmp>/short/silero-vad-ggml-v6.2.0/ggml-silero-v6.2.0.bin has the wrong size after the move",
  "switch.unknownMemory": "This machine's memory is unknown; metal-16gb needs 15000 MiB. The self-test will fall back to the CPU if the GPU cannot run it.",
  "cues.noTranslation": "no Traditional Chinese subtitles yet: the translate step has not finished",
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

const SHELL_VALUES: Readonly<Record<string, string>> = {
  path: "C:\videos\talk.mp4",
  error: "The system cannot find the file specified. (os error 2)",
  name: '"a/b"',
  address: "http://example.com/x",
  host: "example.com",
};

/** What a window in Traditional Chinese shows for each W4b part 2 shell sentence, with `SHELL_VALUES` filled in. */
const SHELL_ZH: Readonly<Record<string, string>> = {
  "shell.file.unreadable": "無法讀取 C:\videos\talk.mp4：The system cannot find the file specified. (os error 2)",
  "shell.file.notMedia": "C:\videos\talk.mp4 不是影片或音訊檔",
  "shell.file.badName": '"a/b" 不是有效的檔案名稱',
  "shell.file.unwritable": "無法寫入 C:\videos\talk.mp4：The system cannot find the file specified. (os error 2)",
  "shell.folder.notOurs": "C:\videos\talk.mp4 不在這個 App 會寫入的資料夾裡，所以不會開啟",
  "shell.folder.missing": "C:\videos\talk.mp4 不存在",
  "shell.link.notPlain": "http://example.com/x 不是標準格式的 https 網址，所以不會開啟",
  "shell.link.hostNotAllowed": "這個 App 不會開啟 example.com 的連結",
};

/** A shell rejection as `notice.rs` makes it: the template filled, and itself as the one notice. */
function fromShell(code: keyof typeof shell): Said {
  const { english, params } = shell[code];
  const message = english.replace(/\{(\w+)\}/g, (_, name: string) => SHELL_VALUES[name]!);
  return { text: message, notices: [{ code, message, params: Object.fromEntries(Object.keys(params).map((n) => [n, SHELL_VALUES[n]!])) }] };
}

describe("every W4b part 2 shell sentence", () => {
  const codes = (Object.keys(shell) as (keyof typeof shell)[]).filter((code) => !(code in shellBefore));

  it("is listed here", () => {
    expect(codes.sort()).toEqual(Object.keys(SHELL_ZH).sort());
  });

  it.each(codes)("%s: English is the shell's sentence, and Traditional Chinese holds no English sentence", (code) => {
    const sent = fromShell(code);
    expect(word(sent, "en")).toBe(sent.text);
    const shown = word(sent, "zh-TW");
    expect(shown).toBe(SHELL_ZH[code]);
    expect(shown.replace(SHELL_VALUES["error"]!, "◇")).not.toMatch(ENGLISH_RUN);
    for (const locale of ["zh-CN", "ja"] as const) expect(word(sent, locale)).not.toBe(sent.text);
  });
});

describe("a move status", () => {
  it("keeps the notices of its error and warnings, so a Chinese window words them", () => {
    const remove = fixture["move.couldNotRemove"];
    const failed = fixture["move.otherContent"];
    const status = parseMove({
      state: "done",
      target: "F:/m",
      files_total: 1,
      files_done: 1,
      bytes_total: 1,
      bytes_done: 1,
      error: failed.text,
      error_notices: failed.notices,
      warnings: [remove.text],
      warnings_notices: remove.notices,
    });

    expect(word(status.warnings[0]!, "zh-TW")).toBe(remove.zh);
    expect(word(status.error!, "zh-TW")).toBe(failed.zh);
  });
});
