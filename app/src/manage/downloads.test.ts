import { describe, expect, it } from "vitest";
import { bytes, shortVersion, speed } from "./format";
import { fraction, isActive, latestByAsset, overall, track } from "./downloads";
import type { DownloadJob } from "./types";

const job = (over: Partial<DownloadJob> = {}): DownloadJob => ({
  id: "j1",
  assetId: "a",
  state: "downloading",
  bytesDone: 50,
  bytesTotal: 100,
  speedBps: 10,
  resumedFrom: 0,
  retries: 0,
  note: null,
  failure: null,
  ...over,
});

describe("download tracking", () => {
  it("keeps the newest job of an asset", () => {
    const map = latestByAsset([job({ id: "old", state: "cancelled" }), job({ id: "new" })]);
    expect(map.get("a")?.id).toBe("new");
  });

  it("reports an asset whose job ended since the last poll", () => {
    const before = latestByAsset([job()]);
    expect(track(before, [job({ state: "done", bytesDone: 100 })]).ended).toEqual(["a"]);
    expect(track(before, [job({ bytesDone: 60 })]).ended).toEqual([]);
  });

  it("does not report an ended job twice", () => {
    const done = job({ state: "done", bytesDone: 100 });
    expect(track(latestByAsset([done]), [done]).ended).toEqual([]);
  });

  it("reports a failed retry that replaced an older ended job", () => {
    const old = job({ id: "old", state: "cancelled" });
    expect(track(latestByAsset([old]), [old, job({ id: "new", state: "failed" })]).ended).toEqual(["a"]);
  });

  it("weights overall progress by size and sums the speed of live jobs only", () => {
    const all = [
      job({ assetId: "a", bytesDone: 100, bytesTotal: 100, state: "done", speedBps: 5 }),
      job({ assetId: "b", bytesDone: 50, bytesTotal: 300, speedBps: 7 }),
    ];
    expect(overall(all)).toEqual({ done: 150, total: 400, fraction: 0.375, speedBps: 7 });
  });

  it("knows which states are live and shows no progress before the size is known", () => {
    expect(isActive(job({ state: "queued" }))).toBe(true);
    expect(isActive(job({ state: "cancelled" }))).toBe(false);
    expect(fraction(job({ bytesTotal: 0 }))).toBe(0);
  });
});

describe("format", () => {
  it("shows sizes and speed in readable units", () => {
    expect(bytes(1549 * 1024 * 1024)).toBe("1.51 GB");
    expect(bytes(0)).toBe("0 B");
    expect(speed(0)).toBe("—");
    expect(speed(3 * 1024 * 1024)).toBe("3.00 MB/s");
    expect(shortVersion("5359861c739e955e79d9a303bcbc70fb988958b1")).toBe("5359861c…");
    expect(shortVersion("b5454")).toBe("b5454");
  });
});
