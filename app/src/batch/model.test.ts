import { describe, expect, it } from "vitest";
import {
  type Batch,
  type BatchItem,
  EMPTY_BATCH,
  actionsFor,
  formatEta,
  moveId,
  overall,
  parseItem,
  parseSnapshot,
  reduceBatch,
  secondsLeft,
  slotAt,
} from "./model";

const raw = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  video_path: `D:\\talks\\${id}.mp4`,
  project_id: `p-${id}`,
  target_lang: "zh-TW",
  state: "queued",
  position: 0,
  step: null,
  progress: 0,
  eta_s: null,
  attempts: 0,
  last_error: null,
  audio_s: null,
  ...over,
});

const item = (id: string, over: Partial<BatchItem> = {}): BatchItem => ({
  id,
  videoPath: `${id}.mp4`,
  projectId: id,
  lang: "zh-TW",
  sourceLang: "en",
  state: "queued",
  position: 0,
  step: null,
  progress: 0,
  etaS: null,
  attempts: 0,
  error: null,
  audioS: null,
  ...over,
});

const ev = (b: Batch, kind: string, data: unknown, replay = false) => reduceBatch(b, { type: "event", kind, data, replay });
const ids = (b: Batch) => b.items.map((i) => i.id);

describe("queue reducer", () => {
  it("loads a snapshot in position order, with settings and the pause flag", () => {
    const b = reduceBatch(EMPTY_BATCH, {
      type: "snapshot",
      snapshot: parseSnapshot({
        paused: true,
        settings: { on_done: "sleep", allow_power: true },
        items: [raw("b", { position: 1 }), raw("a", { position: 0 })],
      }),
    });
    expect(ids(b)).toEqual(["a", "b"]);
    expect(b.paused).toBe(true);
    expect(b.settings).toEqual({ onDone: "sleep", allowPower: true });
    expect(b.loaded).toBe(true);
  });

  it("adds an item from an event and replaces it on the next one", () => {
    let b = ev(EMPTY_BATCH, "item", raw("a"));
    b = ev(b, "item", raw("a", { state: "running", step: "asr", progress: 0.3 }));
    expect(b.items).toHaveLength(1);
    expect(b.items[0]).toMatchObject({ state: "running", step: "asr", progress: 0.3 });
  });

  it("moves a retried item to the end through its new position", () => {
    let b = ev(ev(EMPTY_BATCH, "item", raw("a", { position: 0, state: "failed" })), "item", raw("b", { position: 1 }));
    b = ev(b, "item", raw("a", { position: 2, state: "queued" }));
    expect(ids(b)).toEqual(["b", "a"]);
  });

  it("follows an order event and a removed event", () => {
    let b = [raw("a", { position: 0 }), raw("b", { position: 1 }), raw("c", { position: 2 })].reduce(
      (acc, r) => ev(acc, "item", r),
      EMPTY_BATCH,
    );
    b = ev(b, "order", { ids: ["c", "a", "b"] });
    expect(ids(b)).toEqual(["c", "a", "b"]);
    b = ev(b, "removed", { ids: ["a"] });
    expect(ids(b)).toEqual(["c", "b"]);
  });

  it("drops what it cannot read", () => {
    expect(ev(EMPTY_BATCH, "item", { id: "x" })).toBe(EMPTY_BATCH);
    expect(ev(EMPTY_BATCH, "item", raw("x", { state: "exploded" }))).toBe(EMPTY_BATCH);
    expect(ev(EMPTY_BATCH, "unknown-kind", {})).toBe(EMPTY_BATCH);
  });

  it("takes the queue flag and settings from a queue event", () => {
    const b = ev(EMPTY_BATCH, "queue", { paused: true, settings: { on_done: "shutdown", allow_power: false } });
    expect(b.paused).toBe(true);
    expect(b.settings).toEqual({ onDone: "shutdown", allowPower: false });
  });

  it("runs a countdown from start to cancel, and ends it when the action fires", () => {
    let b = ev(EMPTY_BATCH, "countdown", { action: "sleep", seconds: 60, deadline_ms: 5000 });
    expect(b.countdown).toEqual({ action: "sleep", deadlineMs: 5000 });
    b = ev(b, "countdown_cancelled", { action: "sleep" });
    expect(b.countdown).toBeNull();
    b = ev(b, "countdown", { action: "shutdown", seconds: 60, deadline_ms: 9000 });
    expect(ev(b, "power", { action: "shutdown", executed: true }).countdown).toBeNull();
  });

  it("clears a stale countdown when the snapshot says none runs, and keeps a live one", () => {
    const counting = ev(EMPTY_BATCH, "countdown", { action: "sleep", deadline_ms: 5000 });
    const snap = (countdown: boolean) => ({ type: "snapshot" as const, snapshot: parseSnapshot({ items: [], countdown }) });
    expect(reduceBatch(counting, snap(false)).countdown).toBeNull();
    expect(reduceBatch(counting, snap(true)).countdown).not.toBeNull();
  });

  it("counts a finished queue, but not one replayed from the log of an earlier run", () => {
    const counts = { counts: { done: 3, failed: 1, cancelled: 0 } };
    expect(ev(EMPTY_BATCH, "done", counts, true).finished).toBeNull();
    const b = ev(ev(EMPTY_BATCH, "done", counts), "done", counts);
    expect(b.finished).toEqual({ n: 2, counts: { done: 3, failed: 1, cancelled: 0 } });
  });

  it("tracks the connection", () => {
    expect(reduceBatch(EMPTY_BATCH, { type: "link", link: "live" }).link).toBe("live");
  });
});

describe("reorder helpers", () => {
  it("moves one id to a slot", () => {
    expect(moveId(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(moveId(["a", "b", "c", "d"], 3, 0)).toEqual(["d", "a", "b", "c"]);
    expect(moveId(["a", "b"], 0, 9)).toEqual(["b", "a"]);
  });

  it("finds the slot from the pointer and the other rows' middles", () => {
    expect(slotAt([10, 30, 50], 5)).toBe(0);
    expect(slotAt([10, 30, 50], 35)).toBe(2);
    expect(slotAt([10, 30, 50], 99)).toBe(3);
  });
});

describe("overall progress and ETA", () => {
  it("weights items by audio length and counts failed ones as done", () => {
    const o = overall([
      item("a", { state: "done", audioS: 3000 }),
      item("b", { state: "running", audioS: 1000, progress: 0.5, etaS: 600 }),
      item("c", { state: "failed", audioS: 0 }),
      item("d", { state: "queued", audioS: 1000, etaS: 1500 }),
    ]);
    expect(o.total).toBe(4);
    expect(o.finished).toBe(2);
    expect(o.fraction).toBeCloseTo((3000 + 500 + 1666.67) / (3000 + 1000 + 1666.67 + 1000), 2);
    expect(o.etaS).toBe(1500);
    expect(o.active).toBe(true);
  });

  it("ignores cancelled items and has no ETA before one is known", () => {
    const o = overall([item("a", { state: "cancelled" }), item("b", { state: "queued" })]);
    expect(o).toMatchObject({ total: 1, finished: 0, fraction: 0, etaS: null, active: true });
  });

  it("is idle and empty for an empty queue", () => {
    expect(overall([])).toMatchObject({ total: 0, fraction: 0, active: false, etaS: null });
  });
});

describe("ETA text", () => {
  it("rounds to minutes, then to hours and minutes", () => {
    expect(formatEta(20)).toBe("不到 1 分鐘");
    expect(formatEta(50)).toBe("約 1 分鐘");
    expect(formatEta(12 * 60 + 10)).toBe("約 12 分鐘");
    expect(formatEta(3600)).toBe("約 1 小時");
    expect(formatEta(2 * 3600 + 5 * 60)).toBe("約 2 小時 5 分");
  });

  it("counts a deadline down to zero and no further", () => {
    expect(secondsLeft(60_000, 0)).toBe(60);
    expect(secondsLeft(60_000, 59_100)).toBe(1);
    expect(secondsLeft(60_000, 70_000)).toBe(0);
  });
});

describe("row actions", () => {
  it("offers only what the backend accepts for each state", () => {
    expect(actionsFor("queued")).toEqual(["pause", "cancel"]);
    expect(actionsFor("paused")).toEqual(["resume", "cancel"]);
    expect(actionsFor("failed")).toContain("retry");
    expect(actionsFor("cancelled")).toContain("retry");
    expect(actionsFor("done")).toEqual(["remove"]);
  });
});

describe("the video language of a queue item", () => {
  it("reads source_lang and says English when the backend sends none", () => {
    expect(parseItem(raw("a", { source_lang: "ja" }))?.sourceLang).toBe("ja");
    expect(parseItem(raw("b"))?.sourceLang).toBe("en");
    expect(parseItem(raw("c", { source_lang: "xx" }))?.sourceLang).toBe("en");
  });
});
