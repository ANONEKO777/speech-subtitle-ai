import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { openSeams } from "./seams.mjs";

describe("open seams", () => {
  it("point both logs into the shots folder by default", () => {
    const seams = openSeams("shots", {});
    expect(seams.VST_OPEN_URL_LOG).toBe(join("shots", "open-url.log"));
    expect(seams.VST_OPEN_FOLDER_LOG).toBe(join("shots", "open-folder.log"));
  });

  it("keep a log the caller already chose", () => {
    expect(openSeams("shots", { VST_OPEN_URL_LOG: "x.log", VST_OPEN_FOLDER_LOG: "y.log" })).toEqual({
      VST_OPEN_URL_LOG: "x.log",
      VST_OPEN_FOLDER_LOG: "y.log",
    });
  });
});
