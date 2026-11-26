import { beforeEach, describe, expect, it, vi } from "vitest";
import { setWindowTitle } from "./windowTitle";

const files = async () => (await import("node:fs" as string)) as { readFileSync: (path: string, encoding: string) => string };

const mocks = vi.hoisted(() => ({ setTitle: vi.fn(() => Promise.resolve()), inShell: true }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => {
    if (!mocks.inShell) throw new TypeError("no shell");
    return { setTitle: mocks.setTitle };
  },
}));

beforeEach(() => {
  mocks.setTitle.mockClear();
  mocks.inShell = true;
});

describe("setWindowTitle", () => {
  it("sets the title of the native window", async () => {
    await setWindowTitle("Video Subtitle Translator");
    expect(mocks.setTitle).toHaveBeenCalledWith("Video Subtitle Translator");
  });

  it("is not an error outside the shell", async () => {
    mocks.inShell = false;
    await expect(setWindowTitle("x")).resolves.toBeUndefined();
  });

  it("is allowed by the window's capability, or the shell refuses it without a sound", async () => {
    const capability = JSON.parse((await files()).readFileSync("src-tauri/capabilities/default.json", "utf8")) as { windows: string[]; permissions: string[] };
    expect(capability.windows).toContain("main");
    expect(capability.permissions).toContain("core:window:allow-set-title");
  });
});
