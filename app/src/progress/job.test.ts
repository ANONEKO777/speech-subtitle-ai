import { describe, expect, it } from "vitest";
import { WAITING, reduceJob } from "./job";

describe("reduceJob", () => {
  it("follows progress events and ends on done", () => {
    let view = reduceJob(WAITING, "status", { status: "running" });
    expect(view).toEqual(WAITING);
    view = reduceJob(view, "progress", { step: "asr", fraction: 0.4, overall: 0.1 });
    expect(view).toEqual({ kind: "running", step: "asr", stepFraction: 0.4, overall: 0.1 });
    expect(reduceJob(view, "done", { overall: 1 })).toEqual({ kind: "done" });
  });

  it("reports a failure with its message", () => {
    expect(reduceJob(WAITING, "failed", { error: "boom" })).toEqual({ kind: "failed", error: "boom" });
  });

  it("fails with a message when the stream drops", () => {
    const view = reduceJob(WAITING, "progress", { step: "asr", fraction: 0.4, overall: 0.1 });
    const lost = reduceJob(view, "disconnected", null);
    expect(lost.kind).toBe("failed");
    expect(reduceJob({ kind: "done" }, "disconnected", null)).toEqual({ kind: "done" });
  });
});
