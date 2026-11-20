// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EXPERIMENTAL_HINT } from "../api/targets";
import { SourceBar } from "./SourceBar";

afterEach(cleanup);

const base = { playing: false, busy: false, sourceLang: "en" as const, unavailable: {}, onSourceLang: () => undefined, found: undefined, experimentalPick: false };

describe("the line under the toolbar", () => {
  it("says the picked subtitle language is not yet judged, when it is not", () => {
    render(<SourceBar {...base} experimentalPick />);
    expect(screen.getByTestId("target-hint").textContent).toBe(EXPERIMENTAL_HINT);
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
});
