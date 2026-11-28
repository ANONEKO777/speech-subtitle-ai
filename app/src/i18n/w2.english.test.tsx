// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { bytes, mib, speed } from "../manage/format";
import { macInventory, macView, windowsInventory, windowsView } from "../manage/screens.fixture";
import type { SettingsView } from "../manage/types";
import { ModelsSection } from "../models-page/ModelsSection";
import { StorageCard } from "../models-page/StorageCard";
import { Wizard } from "../wizard/Wizard";
import { I18nProvider, useI18n } from "./I18nProvider";
import { plural, t } from ".";

const mocks = vi.hoisted(() => ({ profile: null as unknown, inventory: null as unknown, settings: null as unknown, move: null as unknown }));

vi.mock("../api/backend", () => ({ pickFolder: () => Promise.resolve(null) }));
vi.mock("../manage/useDownloads", () => ({ useDownloads: () => ({ list: [], byAsset: new Map(), refresh: () => undefined }) }));
vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: () => Promise.resolve(mocks.profile),
  fetchLicenses: () => Promise.resolve([]),
  fetchInventory: () => Promise.resolve(mocks.inventory),
  fetchSettings: () => (typeof mocks.settings === "function" ? mocks.settings() : Promise.resolve(mocks.settings)),
  fetchMove: () => Promise.resolve(mocks.move),
  verifyAsset: () => Promise.resolve({}),
  repairAsset: () => Promise.resolve({ action: "redownload", reason: { text: "SHA256 mismatch", notices: [] }, job: null }),
  redownload: () => new Promise(() => undefined),
  chooseProfile: () => Promise.resolve({ profile: mocks.profile, warnings: [] }),
  downloadProfileAssets: () => Promise.resolve([]),
  runSelfTest: () => Promise.reject(new Error("")),
}));

const backend = { port: 1, token: "t" } as Backend;
const downloads = { list: [], byAsset: new Map(), refresh: () => undefined };
const idle = { state: "idle", target: null, filesTotal: 0, filesDone: 0, bytesTotal: 0, bytesDone: 0, error: null, warnings: [] };
const settings = (modelsDir: string) => ({ storage: { userData: "", modelsDir, customModelsDir: null } }) as unknown as SettingsView;

afterEach(cleanup);

describe("English wording that no other test pins", () => {
  it("names two and three other profiles in words and more in digits", () => {
    expect(t("en", "wizard.others.two")).toBe("two");
    expect(t("en", "wizard.others.three")).toBe("three");
    expect(t("en", "wizard.recommended.post", { others: "two" })).toBe(". You can also choose one of the other two below.");
  });

  it("says item or items installed, and file or files moved", () => {
    expect(plural("en", "models.summary", 1, { size: "1.49 GB" })).toMatch(/^1 item installed, 1\.49 GB in total\./);
    expect(plural("en", "models.summary", 3, { size: "1.49 GB" })).toMatch(/^3 items installed, 1\.49 GB in total\./);
    expect(plural("en", "storage.moving", 1, { percent: 50, filesDone: 0, done: "1 MB", total: "2 MB" })).toBe("Moving 50%: 0 / 1 file, 1 MB / 2 MB");
    expect(plural("en", "storage.moved", 2, { size: "2 MB", target: "F:/x" })).toBe("Move complete: 2 files (2 MB) moved to F:/x");
    expect(plural("en", "storage.confirm.body", 1, { size: "1 MB", notInstalled: "Not installed" })).toContain("1 installed model (1 MB) is in the old folder");
  });

  it("keeps the English wizard's own words on the buttons", async () => {
    mocks.profile = windowsView();
    render(
      <I18nProvider initial="en">
        <Wizard backend={backend} onExit={() => undefined} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("wizard-choose"));
    expect(screen.getByTestId("wizard-start").textContent).toBe("Download and start");
    expect(screen.getByTestId("wizard-skip").textContent).toBe("Skip and set up later in Settings");
    expect(screen.getByTestId("wizard-recommended").textContent).toBe("Recommended profile: 24 GB GPU. You can also choose one of the other two below.");
    expect(screen.getByTestId("wizard-total").textContent).toMatch(/^Total [\d.]+ GB, free disk space 488 GB$/);
    expect(within(screen.getByTestId("wizard-profile-gpu-24gb")).getByText("Recommended")).toBeTruthy();
    expect(screen.getAllByText("Recommended")).toHaveLength(1);
  });

  it("says In use, two short words, on an item the current profile uses", async () => {
    const inventory = windowsInventory();
    mocks.inventory = { ...inventory, assets: inventory.assets.map((a) => (a.state === "installed" ? { ...a, inActiveProfile: true } : a)) };
    render(
      <I18nProvider initial="en">
        <ModelsSection backend={backend} downloads={downloads} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("inv-table"));
    expect(screen.getByTestId("inv-whisper-large-v3-turbo-active").textContent).toBe("In use");
  });

  it("says in English where a Mac builds its own runtime, and counts zero items", async () => {
    mocks.inventory = macInventory();
    render(
      <I18nProvider initial="en">
        <ModelsSection backend={backend} downloads={downloads} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("inv-table"));
    expect(screen.getByTestId("inv-whispercpp-b5454-macos-metal-build").textContent).toBe("built on this Mac by running scripts/mac/build_whisper_cli.sh; see docs/MACOS.md");
    expect(screen.getByTestId("inv-summary").textContent).toMatch(/^0 items installed, 0 B in total\./);
  });
});

describe("the example folder follows the platform of the window", () => {
  const shell = window as unknown as { __TAURI_INTERNALS__?: unknown };
  afterEach(() => {
    delete shell.__TAURI_INTERNALS__;
  });

  const placeholder = async (settingsResult: () => Promise<unknown>, locale: "en" | "zh-TW" = "en") => {
    mocks.settings = settingsResult;
    mocks.move = idle;
    render(
      <I18nProvider initial={locale}>
        <StorageCard backend={backend} onChanged={() => undefined} />
      </I18nProvider>,
    );
    return (screen.getByTestId("models-dir-input") as HTMLInputElement).placeholder;
  };

  it("shows a drive-letter example on Windows", async () => {
    shell.__TAURI_INTERNALS__ = { plugins: { path: { sep: "\\" } } };
    expect(await placeholder(() => Promise.resolve(settings("C:\\Users\\me\\models")))).toBe("New models folder, for example E:\\vst-models");
  });

  it("shows no drive letter on a Mac", async () => {
    shell.__TAURI_INTERNALS__ = { plugins: { path: { sep: "/" } } };
    const text = await placeholder(() => Promise.resolve(settings("/Users/me/Library/Application Support/models")));
    expect(text).toBe("New models folder, for example /Volumes/Models/vst-models");
    expect(text).not.toContain("E:");
  });

  it("shows the example while the settings load and after they fail to load", async () => {
    expect(await placeholder(() => new Promise(() => undefined), "zh-TW")).toBe("新的模型資料夾，例如 E:\\vst-models");
    cleanup();
    expect(await placeholder(() => Promise.reject(new Error("offline")), "zh-TW")).toBe("新的模型資料夾，例如 E:\\vst-models");
    await waitFor(() => screen.getByText("offline"));
    expect((screen.getByTestId("models-dir-input") as HTMLInputElement).placeholder).toBe("新的模型資料夾，例如 E:\\vst-models");
  });
});

describe("sizes and speeds", () => {
  it("print the same digits in every shipped language", () => {
    for (const locale of ["en", "zh-TW", "zh-CN", "ja"] as const) {
      expect(bytes(1_600_000_000, locale)).toBe("1.49 GB");
      expect(speed(5_000_000, locale)).toBe("4.77 MB/s");
      expect(mib(null, locale)).toBe("—");
    }
  });
});

describe("a Mac wizard", () => {
  it("counts three other profiles and says unified memory", async () => {
    mocks.profile = macView();
    render(
      <I18nProvider initial="en">
        <Wizard backend={backend} onExit={() => undefined} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("wizard-choose"));
    expect(screen.getByTestId("wizard-recommended").textContent).toContain("the other three below");
    expect(screen.getByTestId("wizard-hardware").textContent).toContain("Unified memory 36.0 GB");
    fireEvent.click(screen.getByTestId("wizard-profile-apple-cpu"));
    expect(screen.getByTestId("wizard-cpu-note")).toBeTruthy();
  });
});

describe("the note after a verify", () => {
  const id = "whisper-large-v3-turbo";
  const bad = "SHA256 does not match. Choose “Repair”.";

  it.each([
    ["verified", "status", "SHA256 matches. The file is intact."],
    ["corrupt", "alert", bad],
    ["unchecked", "alert", bad],
  ] as const)("reports a file that is %s afterwards as a %s", async (shaState, role, text) => {
    const inventory = windowsInventory();
    mocks.inventory = { ...inventory, assets: inventory.assets.map((a) => (a.id === id ? { ...a, shaState } : a)) };
    render(
      <I18nProvider initial="en">
        <ModelsSection backend={backend} downloads={downloads} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("inv-table"));
    fireEvent.click(screen.getByTestId(`act-${id}-verify`));
    const note = await screen.findByTestId(`inv-${id}-note`);
    expect(note.textContent).toBe(text);
    expect(note.getAttribute("role")).toBe(role);
  });
});

describe("the models page re-words its row notes when the language changes", () => {
  function ToChinese() {
    const i18n = useI18n();
    return <button type="button" data-testid="to-zh" onClick={() => i18n?.setUiLanguage("zh-TW")} />;
  }

  const page = async () => {
    mocks.inventory = windowsInventory();
    render(
      <I18nProvider initial="en">
        <ToChinese />
        <ModelsSection backend={backend} downloads={downloads} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("inv-table"));
  };
  const note = () => screen.getByTestId("inv-whisper-large-v3-turbo-note").textContent;

  it("re-words a verify note", async () => {
    await page();
    fireEvent.click(screen.getByTestId("act-whisper-large-v3-turbo-verify"));
    await waitFor(() => expect(note()).toBe("SHA256 matches. The file is intact."));
    fireEvent.click(screen.getByTestId("to-zh"));
    expect(note()).toBe("SHA256 相符，檔案完整");
  });

  it("re-words a repair note", async () => {
    await page();
    fireEvent.click(screen.getByTestId("act-whisper-large-v3-turbo-repair"));
    await waitFor(() => expect(note()).toBe("Repair: redownload (SHA256 mismatch)"));
    fireEvent.click(screen.getByTestId("to-zh"));
    expect(note()).toBe("修復：redownload（SHA256 mismatch）");
  });

  it("re-words the working line of a running action", async () => {
    await page();
    fireEvent.click(screen.getByTestId("act-whisper-large-v3-turbo-redownload"));
    await screen.findByText("Downloading again…");
    fireEvent.click(screen.getByTestId("to-zh"));
    expect(screen.getByText("重新下載中…")).toBeTruthy();
  });
});

describe("a self-test that fails with no message", () => {
  it("says the self-test reported nothing instead of an empty alert", async () => {
    const view = windowsView();
    mocks.profile = { ...view, profiles: view.profiles.map((p) => ({ ...p, missing: [], downloadBytes: 0 })) };
    render(
      <I18nProvider initial="en">
        <Wizard backend={backend} onExit={() => undefined} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByTestId("wizard-choose"));
    fireEvent.click(screen.getByTestId("wizard-start"));
    await screen.findByTestId("wizard-result");
    expect(screen.getByTestId("wizard-error").textContent).toBe("The self-test did not report a result.");
  });
});
