// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useIdle } from "./useIdle";

const MS = 2500;

/** A stage with a controls bar that holds one button, as the player does. */
function stageWithButton() {
  const stage = document.createElement("div");
  const controls = document.createElement("div");
  controls.className = "controls";
  const button = document.createElement("button");
  controls.append(button);
  const outside = document.createElement("button");
  stage.append(controls, outside);
  document.body.append(stage);
  return { stage, button, outside };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("useIdle", () => {
  it("turns idle a while after the last movement, and not before", () => {
    const { stage } = stageWithButton();
    const { result } = renderHook(() => useIdle({ current: stage }, MS));
    act(() => result.current.wake());
    act(() => void vi.advanceTimersByTime(MS - 1));
    expect(result.current.idle).toBe(false);
    act(() => void vi.advanceTimersByTime(1));
    expect(result.current.idle).toBe(true);
    act(() => result.current.wake());
    expect(result.current.idle).toBe(false);
  });

  it("gives focus back from a control that a mouse press left focused", () => {
    const { stage, button } = stageWithButton();
    const { result } = renderHook(() => useIdle({ current: stage }, MS));
    act(() => {
      button.dispatchEvent(new Event("pointerdown", { bubbles: true }));
      button.focus();
      result.current.wake();
    });
    expect(document.activeElement).toBe(button);
    act(() => void vi.advanceTimersByTime(MS));
    expect(document.activeElement).not.toBe(button);
    expect(result.current.idle).toBe(true);
  });

  it("keeps focus that arrived by Tab, so keyboard users still see the controls", () => {
    const { stage, button } = stageWithButton();
    const { result } = renderHook(() => useIdle({ current: stage }, MS));
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
      button.focus();
      result.current.wake();
    });
    act(() => void vi.advanceTimersByTime(MS));
    expect(document.activeElement).toBe(button);
  });

  it("a mouse press after Tab makes focus pointer-owned again", () => {
    const { stage, button } = stageWithButton();
    const { result } = renderHook(() => useIdle({ current: stage }, MS));
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
      button.dispatchEvent(new Event("pointerdown", { bubbles: true }));
      button.focus();
      result.current.wake();
    });
    act(() => void vi.advanceTimersByTime(MS));
    expect(document.activeElement).not.toBe(button);
  });

  it("leaves focus alone when it is outside the controls", () => {
    const { stage, outside } = stageWithButton();
    const { result } = renderHook(() => useIdle({ current: stage }, MS));
    act(() => {
      outside.focus();
      result.current.wake();
    });
    act(() => void vi.advanceTimersByTime(MS));
    expect(document.activeElement).toBe(outside);
  });
});
