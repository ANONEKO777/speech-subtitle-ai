import { describe, expect, it } from "vitest";
import { EMPTY_QUEUE, dequeue, enqueue, neighbour, parseQueue, playing, pruned } from "./queue";

const q = (ids: string[], current: string | null = null) => ({ ids, current });

describe("play queue", () => {
  it("adds each id once, in order", () => {
    expect(enqueue(enqueue(enqueue(EMPTY_QUEUE, "a"), "b"), "a").ids).toEqual(["a", "b"]);
  });

  it("steps to the previous and next id and stops at the ends", () => {
    const now = q(["a", "b", "c"], "b");
    expect(neighbour(now, 1)).toBe("c");
    expect(neighbour(now, -1)).toBe("a");
    expect(neighbour(q(["a", "b", "c"], "c"), 1)).toBeNull();
    expect(neighbour(q(["a", "b", "c"], "a"), -1)).toBeNull();
  });

  it("has no neighbour when what plays is not in the queue", () => {
    expect(neighbour(playing(q(["a", "b"]), "z"), 1)).toBeNull();
    expect(neighbour(playing(q(["a", "b"]), "a"), 1)).toBe("b");
  });

  it("forgets the current id when it is removed", () => {
    expect(dequeue(q(["a", "b"], "a"), "a")).toEqual(q(["b"], null));
  });

  it("reads a damaged store as empty and drops unknown ids", () => {
    expect(parseQueue("{oops")).toEqual(EMPTY_QUEUE);
    expect(parseQueue(JSON.stringify({ ids: ["a", 3, "a", "b"], current: "x" }))).toEqual(q(["a", "b"]));
    expect(pruned(q(["a", "b"], "b"), new Set(["a"]))).toEqual(q(["a"], null));
  });
});
