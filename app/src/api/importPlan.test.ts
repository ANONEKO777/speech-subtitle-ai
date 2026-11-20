import { describe, expect, it } from "vitest";
import type { ProjectView } from "./client";
import { planImport } from "./importPlan";
import { parseSourceTargets } from "./targets";

const known = {
  languages: [],
  targets: parseSourceTargets([
    {
      code: "ja",
      targets: ["zh-TW", "zh-CN", "en", "ko"].map((code) => ({ code, name: code, native_name: code, experimental: code === "ko" })),
    },
    { code: "ja+en", targets: [{ code: "zh-TW", name: "x", native_name: "x", experimental: false }] },
  ]),
};
const project = (over: Partial<ProjectView>): ProjectView => ({
  id: "p",
  videoPath: "D:/a.mp4",
  translated: true,
  activeJob: null,
  activeLang: "zh-TW",
  translatedLangs: ["zh-TW"],
  sourceLang: "ja",
  failedCues: {},
  ...over,
});

describe("what an import does with the project of the video", () => {
  it("plays a project that has the language asked for", () => {
    expect(planImport(project({}), "ja", "zh-TW", known)).toEqual({ kind: "play", prefer: "zh-TW" });
  });

  it("plays a project as it stands when the import names no language", () => {
    expect(planImport(project({ translatedLangs: ["en"], activeLang: "en" }), null, null, known)).toEqual({ kind: "play", prefer: null });
  });

  it("translates the same video again into a language it does not have, and says only the translation reruns", () => {
    expect(planImport(project({}), "ja", "en", known)).toEqual({ kind: "run", source: "ja", target: "en", addsTarget: true });
  });

  it("uses the video language the project was made with, not the one now picked", () => {
    expect(planImport(project({}), "en", "ko", known)).toEqual({ kind: "run", source: "ja", target: "ko", addsTarget: true });
  });

  it("asks for the first language a project of a mixed talk has when the one wanted is not its own", () => {
    expect(planImport(project({ sourceLang: "ja+en" }), "ja+en", "ko", known)).toEqual({ kind: "play", prefer: "zh-TW" });
  });

  it("runs a new project from the start, in the video language picked", () => {
    const fresh = project({ translated: false, translatedLangs: [], sourceLang: "en" });
    expect(planImport(fresh, "ja", "ko", known)).toEqual({ kind: "run", source: "ja", target: "ko", addsTarget: false });
  });

  it("follows a job that is running instead of playing", () => {
    expect(planImport(project({ activeJob: "j1" }), "ja", "zh-TW", known).kind).toBe("run");
  });
});
