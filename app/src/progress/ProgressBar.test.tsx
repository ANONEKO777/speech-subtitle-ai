// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProgressBar } from "./ProgressBar";

afterEach(cleanup);
const running = { kind: "running", step: "translate", stepFraction: 0.5, overall: 0.7 } as const;

describe("the progress of a run", () => {
  it("names the language the translate step translates into", () => {
    render(<ProgressBar view={running} target="English" />);
    expect(screen.getByTestId("step-name").textContent).toBe("翻譯成English（5/7）");
  });

  it("says the speech steps are kept when a run only adds a language", () => {
    render(<ProgressBar view={running} target="简体中文" addsTarget />);
    expect(screen.getByTestId("rerun-note").textContent).toContain("只會重新翻譯成简体中文");
    const kept = [...document.querySelectorAll(".steps li")].map((li) => li.getAttribute("data-kept"));
    expect(kept).toEqual(["true", "true", "true", "true", "false", "false", "false"]);
  });

  it("says nothing of the kind on a first run", () => {
    render(<ProgressBar view={running} target="繁體中文" />);
    expect(screen.queryByTestId("rerun-note")).toBeNull();
  });
});
