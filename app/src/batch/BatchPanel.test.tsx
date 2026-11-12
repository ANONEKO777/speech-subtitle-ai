// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BatchPanel } from "./BatchPanel";
import { EMPTY_BATCH, type Batch, type BatchItem } from "./model";

const reorder = vi.fn<(ids: readonly string[]) => Promise<unknown>>();
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  reorderQueue: (_b: unknown, ids: readonly string[]) => reorder(ids),
}));

const backend = { port: 1, token: "t" };
const item = (id: string): BatchItem => ({
  id,
  videoPath: `C:/v/${id}.mp4`,
  lang: "zh-TW",
  sourceLang: "en",
  state: "queued",
  step: null,
  progress: 0,
  etaS: null,
  error: null,
  attempts: 0,
}) as BatchItem;
const batch: Batch = { ...EMPTY_BATCH, loaded: true, items: ["a", "b", "c"].map(item) };

const order = () => [...document.querySelectorAll("li.batch-row")].map((li) => (li as HTMLElement).dataset["rowId"]);

beforeEach(() => {
  reorder.mockResolvedValue(undefined);
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const i = order().indexOf((this as HTMLElement).dataset["rowId"] ?? "");
    return { top: i * 100, bottom: i * 100 + 100, height: 100 } as DOMRect;
  });
  render(<BatchPanel backend={backend} batch={batch} languages={[]} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  reorder.mockReset();
});

const grab = (id: string) => fireEvent.pointerDown(screen.getByTestId(`qdrag-${id}`), { button: 0, clientY: 10 });

describe("dragging a queue row", () => {
  it("sends the new order when the pointer is released away from the handle after a move down", () => {
    grab("a");
    fireEvent.pointerMove(window, { clientY: 250 });
    expect(order()).toEqual(["b", "c", "a"]);
    fireEvent.pointerUp(window, { clientY: 250 });
    expect(reorder).toHaveBeenCalledWith(["b", "c", "a"]);
    expect(document.querySelector("[data-dragging='true']")).toBeNull();
  });

  it("sends the new order for a move up", () => {
    grab("c");
    fireEvent.pointerMove(window, { clientY: -5 });
    fireEvent.pointerUp(window, { clientY: -5 });
    expect(reorder).toHaveBeenCalledWith(["c", "a", "b"]);
  });

  it("goes back to the server order on cancel, with no request", () => {
    grab("a");
    fireEvent.pointerMove(window, { clientY: 250 });
    fireEvent.pointerCancel(window);
    expect(reorder).not.toHaveBeenCalled();
    expect(order()).toEqual(["a", "b", "c"]);
    expect(document.querySelector("[data-dragging='true']")).toBeNull();
  });

  it("sends nothing when the row is dropped where it started", () => {
    grab("b");
    fireEvent.pointerMove(window, { clientY: 140 });
    fireEvent.pointerUp(window, { clientY: 140 });
    expect(reorder).not.toHaveBeenCalled();
  });
});

describe("a running queue row", () => {
  it("does not start a drag from its disabled handle", () => {
    cleanup();
    const running: Batch = { ...batch, items: [{ ...item("a"), state: "running" } as BatchItem, item("b"), item("c")] };
    render(<BatchPanel backend={backend} batch={running} languages={[]} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />);
    grab("a");
    fireEvent.pointerMove(window, { clientY: 250 });
    fireEvent.pointerUp(window, { clientY: 250 });
    expect(reorder).not.toHaveBeenCalled();
    expect(order()).toEqual(["a", "b", "c"]);
  });
});
