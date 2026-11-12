// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SourcePick } from "./ImportPanel";

afterEach(cleanup);

describe("the video language picker", () => {
  it("offers three choices, and the mixed one is picked like the others", () => {
    const onSourceLang = vi.fn();
    render(<SourcePick busy={false} sourceLang="en" unavailable={{}} onSourceLang={onSourceLang} />);
    const select = screen.getByTestId("source-lang") as HTMLSelectElement;
    expect([...select.options].map((o) => o.label)).toEqual(["英文", "日文", "日文與英文混合"]);
    fireEvent.change(select, { target: { value: "ja+en" } });
    expect(onSourceLang).toHaveBeenCalledWith("ja+en");
  });

  it("shows the mixed choice disabled with the reason when this machine cannot run it", () => {
    const why = "這台電腦沒有安裝混合語言所需的模型";
    render(<SourcePick busy={false} sourceLang="en" unavailable={{ "ja+en": why }} onSourceLang={() => undefined} />);
    const options = [...(screen.getByTestId("source-lang") as HTMLSelectElement).options];
    const mixed = options.find((o) => o.value === "ja+en");
    expect(mixed?.disabled).toBe(true);
    expect(mixed?.textContent).toBe(`日文與英文混合（${why}）`);
    expect(mixed?.title).toBe(why);
  });
});
