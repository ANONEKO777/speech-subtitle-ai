import { describe, expect, it } from "vitest";
import type { DownloadJob, ProfileOption, ProfileView, SelfTest } from "../manage/types";
import { needsWizard } from "./firstRun";
import { downloadPlan } from "./plan";
import { type WizardEvent, type WizardState, initialWizard, reduceWizard } from "./flow";
import { plainText } from "../i18n/said";

const option = (id: ProfileOption["id"], over: Partial<ProfileOption> = {}): ProfileOption => ({
  id,
  label: id,
  recommendCloud: id === "cpu",
  fitsHardware: true,
  active: false,
  recommended: id === "gpu-24gb",
  missing: [],
  downloadBytes: 0,
  asrModel: "a",
  llmModel: "l",
  ...over,
});
const view: ProfileView = {
  vcRuntimeMissing: false,
  hardware: { platform: "win-x64", chip: null, gpuName: "RTX 4090", vramMib: 24564, driverVersion: "596.36", ramMib: 65536, diskFreeMib: 500000 },
  recommended: { id: "gpu-24gb", label: "24 GB", why: plainText("fits") },
  active: { id: "gpu-24gb", label: "24 GB", source: "recommended", device: "cuda" },
  profiles: [option("gpu-24gb"), option("gpu-8gb"), option("cpu")],
  fallback: null,
};
const job = (id: string, state: DownloadJob["state"], failure: DownloadJob["failure"] = null): DownloadJob => ({
  id,
  assetId: `asset-${id}`,
  state,
  bytesDone: 0,
  bytesTotal: 10,
  speedBps: 0,
  resumedFrom: 0,
  retries: 0,
  note: null,
  failure,
});
const test = (over: Partial<SelfTest> = {}): SelfTest => ({ ok: true, device: "cuda", stages: [], fallback: null, seconds: 6, message: plainText("ok"), ...over });

const run = (events: WizardEvent[], from: WizardState = initialWizard) => events.reduce(reduceWizard, from);
const toDownload: WizardEvent[] = [{ type: "loaded", view }, { type: "start" }];

describe("first-run wizard", () => {
  it("starts on the recommended profile and lets the person pick another", () => {
    const s = run([{ type: "loaded", view }, { type: "select", profile: "cpu" }]);
    expect(s).toMatchObject({ step: "choose", selected: "cpu" });
    expect(run([{ type: "loaded", view }])).toMatchObject({ selected: "gpu-24gb" });
  });

  it("goes download, self-test, result and finishes when the test passes", () => {
    const s = run([
      ...toDownload,
      { type: "started", jobIds: ["1", "2"] },
      { type: "polled", jobs: [job("1", "done"), job("2", "downloading")] },
      { type: "polled", jobs: [job("1", "done"), job("2", "done")] },
      { type: "selfTested", test: test() },
      { type: "finish" },
    ]);
    expect(s.step).toBe("finished");
  });

  it("skips the download when nothing is missing", () => {
    expect(run([...toDownload, { type: "started", jobIds: [] }]).step).toBe("selftest");
  });

  it("falls back to the CPU with the reason and still lets the person go on", () => {
    const fallback = test({ device: "cpu", fallback: { reason: plainText("CUDA failed to initialise") }, message: plainText("The CPU backend is used instead.") });
    const s = run([...toDownload, { type: "started", jobIds: ["1"] }, { type: "polled", jobs: [job("1", "done")] }, { type: "selfTested", test: fallback }]);
    expect(s).toMatchObject({ step: "result", test: { device: "cpu", fallback: { reason: plainText("CUDA failed to initialise") } } });
    expect(reduceWizard(s, { type: "finish" }).step).toBe("finished");
  });

  it("does not finish on a failed self-test, and can test again or change the profile", () => {
    const s = run([...toDownload, { type: "started", jobIds: [] }, { type: "selfTested", test: test({ ok: false }) }]);
    expect(reduceWizard(s, { type: "finish" })).toBe(s);
    expect(reduceWizard(s, { type: "rerunSelfTest" }).step).toBe("selftest");
    expect(reduceWizard(s, { type: "back" }).step).toBe("choose");
    const broken = run([...toDownload, { type: "started", jobIds: [] }, { type: "selfTestFailed", error: plainText("x") }]);
    expect(reduceWizard(broken, { type: "finish" })).toBe(broken);
  });

  it("stops on a cancel and resumes on retry", () => {
    const running = run([...toDownload, { type: "started", jobIds: ["1"] }]);
    const cancelled = reduceWizard(running, { type: "cancelDownload" });
    expect(cancelled).toMatchObject({ step: "download", phase: "cancelled" });
    expect(reduceWizard(cancelled, { type: "polled", jobs: [job("1", "done")] })).toBe(cancelled);
    expect(reduceWizard(cancelled, { type: "retry" })).toMatchObject({ phase: "starting", jobIds: [] });
    expect(reduceWizard(cancelled, { type: "back" }).step).toBe("choose");
  });

  it("notices a cancel that came from the backend", () => {
    const s = run([...toDownload, { type: "started", jobIds: ["1", "2"] }, { type: "polled", jobs: [job("1", "cancelled"), job("2", "downloading")] }]);
    expect(s).toMatchObject({ phase: "cancelled" });
  });

  it("shows the failure message of a failed download", () => {
    const failure = { kind: "network", message: "connection lost" };
    const s = run([...toDownload, { type: "started", jobIds: ["1"] }, { type: "polled", jobs: [job("1", "failed", failure)] }]);
    expect(s).toMatchObject({ phase: "failed", error: { assetId: "asset-1", message: "connection lost" } });
  });

  it("ignores jobs that belong to something else", () => {
    const s = run([...toDownload, { type: "started", jobIds: ["1"] }, { type: "polled", jobs: [job("9", "failed", { kind: "io", message: "x" })] }]);
    expect(s).toMatchObject({ phase: "running" });
  });

  it("lets the person leave the wizard at any step, but not undo a finished one", () => {
    expect(run([{ type: "loaded", view }, { type: "skip" }]).step).toBe("skipped");
    expect(run([...toDownload, { type: "started", jobIds: ["1"] }, { type: "skip" }]).step).toBe("skipped");
    const finished = run([...toDownload, { type: "started", jobIds: [] }, { type: "selfTested", test: test() }, { type: "finish" }]);
    expect(reduceWizard(finished, { type: "skip" })).toBe(finished);
  });

  it("reports a failed detection and recovers when it loads again", () => {
    const failed = run([{ type: "loadFailed", error: plainText("no backend") }]);
    expect(failed).toMatchObject({ step: "detect-failed", error: plainText("no backend") });
    expect(reduceWizard(failed, { type: "loaded", view }).step).toBe("choose");
  });
});

describe("who sees the wizard", () => {
  const model = (kind: string, state: string) => ({ kind, state });
  it("shows it when no ASR model and no LLM are installed", () => {
    expect(needsWizard([model("asr", "not_installed"), model("llm", "not_installed"), model("vad", "installed")], false)).toBe(true);
  });
  it("does not show it to a user who has both", () => {
    expect(needsWizard([model("asr", "installed"), model("llm", "installed")], false)).toBe(false);
  });
  it("shows it for a half download", () => {
    expect(needsWizard([model("asr", "partial"), model("llm", "installed")], false)).toBe(true);
  });
  it("respects a skip", () => {
    expect(needsWizard([], true)).toBe(false);
  });
});

describe("download plan", () => {
  const miss = (id: string, type: string, sizeBytes: number) => ({ id, type, sizeBytes, localBuild: false });
  const planView: ProfileView = {
    ...view,
    profiles: [
      option("gpu-24gb", { missing: [miss("whisper", "model", 100), miss("whisper-cuda", "runtime", 50)] }),
      option("gpu-8gb", { missing: [miss("qwen3-asr", "model", 70)] }),
      option("cpu", { missing: [miss("whisper", "model", 100), miss("whisper-cpu", "runtime", 8), miss("llama-cpu", "runtime", 23)] }),
    ],
  };

  it("adds the CPU runtimes, and only those, to a GPU profile", () => {
    const plan = downloadPlan(planView, "gpu-24gb");
    expect(plan.items.map((i) => [i.id, i.fallback])).toEqual([
      ["whisper", false],
      ["whisper-cuda", false],
      ["whisper-cpu", true],
      ["llama-cpu", true],
    ]);
    expect(plan.totalBytes).toBe(100 + 50 + 8 + 23);
  });

  it("lists exactly the missing assets of the CPU profile", () => {
    expect(downloadPlan(planView, "cpu").items.map((i) => i.id)).toEqual(["whisper", "whisper-cpu", "llama-cpu"]);
  });

  it("swaps the list when the person picks the 8 GB profile", () => {
    expect(downloadPlan(planView, "gpu-8gb").items.map((i) => i.id)).toEqual(["qwen3-asr", "whisper-cpu", "llama-cpu"]);
  });
});
