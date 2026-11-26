// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { isMacShell } from "./platform";

const shell = window as unknown as { __TAURI_INTERNALS__?: unknown };

afterEach(() => {
  delete shell.__TAURI_INTERNALS__;
});

describe("isMacShell", () => {
  it("reads the path separator the shell reports", () => {
    shell.__TAURI_INTERNALS__ = { plugins: { path: { sep: "/" } } };
    expect(isMacShell()).toBe(true);
    shell.__TAURI_INTERNALS__ = { plugins: { path: { sep: "\\" } } };
    expect(isMacShell()).toBe(false);
  });

  it("speaks as Windows outside the shell", () => {
    expect(isMacShell()).toBe(false);
  });
});
