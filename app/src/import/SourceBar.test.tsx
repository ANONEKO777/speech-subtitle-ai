// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tZhTW } from "../i18n";
import { SourceBar } from "./SourceBar";

afterEach(cleanup);

const base = { playing: false, busy: false, sourceLang: "en" as const, unavailable: {}, onSourceLang: () => undefined, found: undefined, experimentalPick: false };

describe("the line under the toolbar", () => {
  it("says the picked subtitle language is not yet judged, when it is not", () => {
    render(<SourceBar {...base} experimentalPick />);
    expect(screen.getByTestId("target-hint").textContent).toBe(tZhTW("targets.experimentalHint"));
  });

  it("is not there when there is nothing to say", () => {
    const { container } = render(<SourceBar {...base} />);
    expect(container.firstChild).toBeNull();
  });

  it("keeps the note of the video language beside the hint", () => {
    render(<SourceBar {...base} sourceLang="ja+en" experimentalPick />);
    expect(screen.getByTestId("source-note")).toBeTruthy();
    expect(screen.getByTestId("target-hint")).toBeTruthy();
  });

  it("holds the video language picker in the player, where the toolbar has no room for it, and nowhere else", () => {
    const onSourceLang = vi.fn();
    const { rerender } = render(<SourceBar {...base} playing sourceLang="ja" onSourceLang={onSourceLang} />);
    fireEvent.change(screen.getByTestId("source-lang"), { target: { value: "en" } });
    expect(onSourceLang).toHaveBeenCalledWith("en");
    rerender(<SourceBar {...base} playing={false} sourceLang="ja" onSourceLang={onSourceLang} />);
    expect(screen.queryByTestId("source-lang")).toBeNull();
  });
});
