// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type Backend } from "../api/client";
import { macInventory, macView, windowsInventory, windowsView, licenses } from "../manage/screens.fixture";
import type { Asset, DownloadJob, Inventory, MoveStatus, ProfileView, SelfTest, SettingsView, UpdateReport } from "../manage/types";
import { DeleteDialog } from "../models-page/DeleteDialog";
import { ModelsSection } from "../models-page/ModelsSection";
import { StorageCard } from "../models-page/StorageCard";
import { SettingsPageAlone } from "../settings/updateTestkit";
import { Wizard } from "../wizard/Wizard";
import { I18nProvider } from "./I18nProvider";
import type { Locale } from "./locale";
import { NOT_ENGLISH } from "./notEnglish";
import { plainText } from "./said";

/**
 * Every W2 screen (the first-run wizard and the models page) rendered in each released language.
 * Traditional Chinese must equal what the screens said before the catalog (`w2.screens.zh-TW.fixture.json`,
 * written from `main` with W2_FIXTURE=write), and English must hold no Chinese or Japanese characters.
 * The stubs carry Latin text only, so a CJK character on the English render is text the catalog did not carry.
 */

const mocks = vi.hoisted(() => ({
  profile: null as unknown,
  profileMode: "ok" as "ok" | "pending" | "fail",
  licenses: [] as readonly unknown[],
  change: new Promise<unknown>(() => undefined) as Promise<unknown>,
  chooseMode: "ok" as "ok" | "pending",
  startMode: "ok" as "ok" | "fail" | "none",
  selfTests: [] as unknown[],
  selfTestMode: "queue" as "queue" | "pending" | "reject",
  dl: { list: [] as unknown[], byAsset: new Map(), refresh: () => undefined },
  inventory: null as unknown,
  inventoryMode: "ok" as "ok" | "pending" | "fail",
  updates: null as unknown,
  updatesMode: "ok" as "ok" | "fail",
  verifiedInventory: null as unknown,
  action: "ok" as "ok" | "pending" | "refuse",
  repair: { action: "redownload", reason: "SHA256 mismatch", job: null } as unknown,
  deleteMode: "ok" as "ok" | "refuse" | "refuse-force" | "refuse-plain" | "fail",
  settings: null as unknown,
  move: { state: "idle", target: null, filesTotal: 0, filesDone: 0, bytesTotal: 0, bytesDone: 0, error: null, warnings: [] } as unknown,
  setDirMode: "ok" as "ok" | "fail",
  moveStartMode: "ok" as "ok" | "fail",
  picked: null as string | null,
}));

const backend = { port: 1, token: "t" } as Backend;

vi.mock("@tauri-apps/api/core", () => ({ convertFileSrc: (p: string) => p, invoke: () => Promise.resolve(null) }));
vi.mock("../api/backend", () => ({ pickFolder: () => Promise.resolve(mocks.picked) }));
vi.mock("../manage/useDownloads", () => ({ useDownloads: () => mocks.dl }));
vi.mock("../manage/api", async (orig) => {
  const real = await orig<typeof import("../manage/api")>();
  const never = () => new Promise<never>(() => undefined);
  return {
    ...real,
    fetchProfile: () => (mocks.profileMode === "pending" ? never() : mocks.profileMode === "fail" ? Promise.reject(new Error("Backend is not ready")) : Promise.resolve(mocks.profile)),
    fetchLicenses: () => Promise.resolve(mocks.licenses),
    fetchLastSelfTest: () => Promise.resolve(null),
    chooseProfile: () => (mocks.chooseMode === "pending" ? never() : Promise.resolve({ profile: mocks.profile, warnings: [] })),
    downloadProfileAssets: () => (mocks.startMode === "fail" ? Promise.reject(new Error("Disk is read-only")) : Promise.resolve(mocks.startMode === "none" ? [] : [{ id: "j1" }, { id: "j2" }])),
    startAsset: () => Promise.resolve({ id: "j3" }),
    cancelDownload: () => Promise.resolve(),
    runSelfTest: () => {
      if (mocks.selfTestMode === "pending") return never();
      if (mocks.selfTestMode === "reject") return Promise.reject(new Error("Self-test crashed"));
      return Promise.resolve(mocks.selfTests.shift());
    },
    fetchInventory: () => {
      if (mocks.inventoryMode === "pending") return never();
      if (mocks.inventoryMode === "fail") return Promise.reject(new Error("Backend is not ready"));
      return Promise.resolve(mocks.action === "ok" || !mocks.verifiedInventory ? mocks.inventory : mocks.verifiedInventory);
    },
    checkUpdates: () => (mocks.updatesMode === "fail" ? Promise.reject(new Error("No network")) : Promise.resolve(mocks.updates)),
    verifyAsset: () => Promise.resolve({}),
    repairAsset: () => Promise.resolve(mocks.repair),
    redownload: () => (mocks.action === "pending" ? never() : Promise.reject(new ApiError(409, "Another download is running", [], { blockers: ["whisper-large-v3-turbo is downloading"] }))),
    updateAsset: () => never(),
    deleteAsset: (_b: unknown, _a: unknown, force?: unknown) => {
      if (mocks.deleteMode === "ok") return Promise.resolve();
      if (mocks.deleteMode === "fail" || force) return Promise.reject(new ApiError(500, "The file is locked by another program"));
      const detail = mocks.deleteMode === "refuse-plain" ? { blockers: [] } : { blockers: ["The active profile needs it", "A download is using it"], can_force: mocks.deleteMode === "refuse-force" };
      return Promise.reject(new ApiError(409, "This item is in use", [], detail));
    },
    fetchSettings: () => Promise.resolve(mocks.settings),
    fetchMove: () => Promise.resolve(mocks.move),
    startMove: () => (mocks.moveStartMode === "fail" ? Promise.reject(new Error("Target is not empty")) : Promise.resolve({ ...(mocks.move as object), state: "running", filesTotal: 3, filesDone: 1, bytesTotal: 2_000_000_000, bytesDone: 500_000_000 })),
    setModelsDir: () => (mocks.setDirMode === "fail" ? Promise.reject(new Error("Folder is not writable")) : Promise.resolve({ warnings: ["The folder is on a network drive"] })),
  };
});

const ATTRS = ["title", "aria-label", "placeholder", "alt", "label"] as const;
interface Harvest {
  readonly text: string;
  readonly attrs: readonly string[];
}

function harvest(root: Element): Harvest {
  const text = (root.textContent ?? "").replace(/\s+/g, " ").trim();
  const attrs: string[] = [];
  for (const node of [root, ...root.querySelectorAll("*")]) {
    for (const name of ATTRS) {
      const value = node.getAttribute(name);
      if (value) attrs.push(`${name}=${value}`);
    }
  }
  return { text, attrs };
}


const FIXTURE = "src/i18n/w2.screens.zh-TW.fixture.json";
const WRITE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["W2_FIXTURE"] === "write";
interface Files {
  readFileSync: (path: string, encoding: string) => string;
  writeFileSync: (path: string, data: string, encoding: string) => void;
}
const files = async () => (await import("node:fs" as string)) as Files;
const written: Record<string, Harvest[]> = {};

const click = (id: string) => fireEvent.click(screen.getByTestId(id));
const typeInto = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });
const wrap = (locale: Locale, node: ReactNode) => <I18nProvider initial={locale}>{node}</I18nProvider>;

type Shot = (name: string, root?: Element) => void;
type Screen = (shot: Shot, locale: Locale) => Promise<void>;

const job = (over: Partial<DownloadJob>): DownloadJob => ({
  id: "j1",
  assetId: "whisper-large-v3-turbo",
  state: "downloading",
  bytesDone: 400_000_000,
  bytesTotal: 1_600_000_000,
  speedBps: 5_000_000,
  resumedFrom: 100_000_000,
  retries: 2,
  note: null,
  failure: null,
  ...over,
});

const run = (over: Partial<SelfTest>): SelfTest => ({ ok: true, device: "cuda", stages: [], fallback: null, seconds: 4.2, message: plainText("ok"), ...over });
const stage = (name: string, ok: boolean) => ({ stage: name, runtimeId: `${name}-rt`, device: "cuda", installed: true, ok, seconds: 1.5, detail: plainText("driver too old") });

const setList = (list: readonly DownloadJob[]) => {
  mocks.dl = { list: [...list], byAsset: new Map(), refresh: () => undefined };
};

const plain = (view: ProfileView, over: Partial<ProfileView["hardware"]> = {}): ProfileView => ({ ...view, hardware: { ...view.hardware, ...over } });

async function wizard(locale: Locale, view: ProfileView) {
  mocks.profile = view;
  mocks.licenses = licenses;
  const out = render(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
  await screen.findByTestId("wizard-choose");
  return out;
}

const asset = (id: string, type: Asset["type"], over: Partial<Asset> = {}): Asset => ({
  id,
  type,
  kind: type === "model" ? "asr" : "whisper.cpp",
  state: "not_installed",
  version: "1",
  installedVersion: null,
  sizeBytes: 0,
  sizeOnDisk: null,
  path: null,
  shaState: "not_installed",
  shaScope: type === "model" ? "file" : "archive_at_install",
  usedByProfiles: [],
  inActiveProfile: false,
  dependents: [],
  blockers: [],
  license: "MIT",
  licenseUrl: "https://spdx.org/licenses/MIT.html",
  localBuild: false,
  foundOutsideRuntimes: false,
  ...over,
});

const richInventory = (): Inventory => ({
  activeProfile: "gpu-24gb",
  modelsDir: "C:/m",
  runtimesDir: "C:/r",
  installedBytes: 4_800_000_000,
  assets: [
    asset("whisper-large-v3-turbo", "model", { state: "installed", sizeBytes: 1_600_000_000, sizeOnDisk: 1_600_000_000, path: "C:/m/whisper-large-v3-turbo.bin", shaState: "verified", installedVersion: "1", usedByProfiles: ["gpu-24gb", "gpu-8gb"], inActiveProfile: true, dependents: [{ id: "whispercpp-b5454-win-cuda", installed: true }, { id: "whispercpp-b5454-win-cpu", installed: false }], blockers: ["The active profile needs it"] }),
    asset("qwen3-8b-q4_k_m", "model", { kind: "llm", state: "installed", sizeBytes: 5_000_000_000, sizeOnDisk: 5_000_000_000, path: "C:/m/qwen3-8b-q4_k_m.gguf", shaState: "corrupt", installedVersion: null }),
    asset("qwen3-asr-1.7b", "model", { state: "partial", sizeBytes: 2_000_000_000, sizeOnDisk: 700_000_000, path: "C:/m/qwen3-asr.part" }),
    asset("whispercpp-b5454-win-cuda", "runtime", { state: "installed", sizeBytes: 480_000_000, sizeOnDisk: 520_000_000, path: "C:/r/whispercpp-b5454-win-cuda", shaState: "verified", installedVersion: "0123456789abcdef0123", version: "0123456789abcdef9999", usedByProfiles: ["gpu-24gb"], inActiveProfile: true }),
    asset("llama.cpp-b12068-win-cuda", "runtime", { state: "installing", sizeBytes: 300_000_000, usedByProfiles: ["gpu-24gb", "cpu"] }),
    asset("whispercpp-b5454-win-cpu", "runtime", { sizeBytes: 9_000_000, usedByProfiles: ["cpu"] }),
    asset("crispasr-v0.8.49-win-cuda", "runtime", { state: "installed", sizeBytes: 90_000_000, sizeOnDisk: 91_000_000, path: "C:/r/crispasr", shaState: "unchecked", installedVersion: "2" }),
    asset("whispercpp-b5454-macos-metal", "runtime", { localBuild: true }),
    asset("llama-b8000-macos-metal", "runtime", { state: "installed", localBuild: true, sizeOnDisk: 800_000, path: "/r/llama-server", shaState: "unchecked", installedVersion: "b8000" }),
    asset("whisper-cli-homebrew", "runtime", { state: "installed", localBuild: true, foundOutsideRuntimes: true, sizeOnDisk: 800_000, path: "/opt/homebrew/bin/whisper-cli", shaState: "unchecked", installedVersion: "b5454" }),
  ],
});

const reportOf = (): UpdateReport => ({
  message: plainText("Checked the registry"),
  items: [
    { id: "whisper-large-v3-turbo", status: "update_available", installable: true, message: plainText("A newer file is listed") },
    { id: "qwen3-8b-q4_k_m", status: "update_available", installable: false, message: plainText("Needs a newer app") },
    { id: "whispercpp-b5454-win-cuda", status: "current", installable: true, message: plainText("") },
    { id: "crispasr-v0.8.49-win-cuda", status: "not_installed", installable: false, message: plainText("") },
    { id: "llama-b8000-macos-metal", status: "unknown", installable: false, message: plainText("") },
    { id: "whisper-cli-homebrew", status: "unknown", installable: false, message: plainText("") },
  ],
});

const settingsView = (modelsDir = "C:/m", custom: string | null = null): SettingsView =>
  ({ uiLanguage: "zh-TW", llm: {}, consentText: "", problem: null, storage: { userData: "C:/u", modelsDir, customModelsDir: custom } }) as unknown as SettingsView;

const SCREENS: Record<string, Screen> = {
  "wizard: detecting and a failed detection": async (shot, locale) => {
    mocks.profileMode = "pending";
    const first = render(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
    shot("detecting", first.container);
    first.unmount();
    mocks.profileMode = "fail";
    const second = render(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
    await screen.findByTestId("wizard-skip");
    shot("detection failed", second.container);
  },
  "wizard: the profile step on a PC": async (shot, locale) => {
    const { container } = await wizard(locale, windowsView());
    await screen.findByTestId("wizard-license-whisper-large-v3-turbo");
    shot("recommended", container);
    click("wizard-profile-cpu");
    shot("cpu picked, with the cloud advice", container);
    click("wizard-profile-gpu-8gb");
    shot("8 GB picked", container);
  },
  "wizard: a PC that is short of everything": async (shot, locale) => {
    const view = plain({ ...windowsView(), vcRuntimeMissing: true, profiles: windowsView().profiles.map((p) => (p.id === "gpu-24gb" ? { ...p, fitsHardware: false } : p)) }, { vramMib: null, driverVersion: null, ramMib: null, diskFreeMib: 1000 });
    const { container } = await wizard(locale, view);
    shot("no vc runtime, tight disk, unknown memory", container);
  },
  "wizard: a PC that has everything": async (shot, locale) => {
    const view = { ...windowsView(), profiles: windowsView().profiles.map((p) => ({ ...p, missing: [], downloadBytes: 0 })) };
    const { container } = await wizard(locale, plain(view, { diskFreeMib: null }));
    shot("nothing missing, disk unknown", container);
  },
  "wizard: the profile step on a Mac": async (shot, locale) => {
    const { container } = await wizard(locale, macView());
    shot("recommended", container);
    click("wizard-profile-apple-cpu");
    shot("processor only picked", container);
    const buildOnly = macView();
    const only = { ...buildOnly, profiles: buildOnly.profiles.map((p) => ({ ...p, missing: p.missing.filter((m) => m.localBuild), downloadBytes: 0 })) };
    cleanup();
    const second = await wizard(locale, only);
    shot("only the local build is missing", second.container);
  },
  "wizard: the download": async (shot, locale) => {
    setList([]);
    mocks.chooseMode = "pending";
    const { container } = await wizard(locale, windowsView());
    click("wizard-start");
    await screen.findByTestId("wizard-download");
    shot("starting", container);
    mocks.chooseMode = "ok";
    cleanup();
    const second = await wizard(locale, windowsView());
    const rerender = second.rerender;
    click("wizard-start");
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("running"));
    shot("running, no job listed yet", second.container);
    setList([job({}), job({ id: "j2", assetId: "whispercpp-b5454-win-cuda", state: "verifying", bytesDone: 480_000_000, bytesTotal: 480_000_000, speedBps: 0, resumedFrom: 0, retries: 0 }), job({ id: "j3", assetId: "whispercpp-b5454-win-cpu", state: "queued", bytesDone: 0, bytesTotal: 9_000_000, speedBps: 0, resumedFrom: 0, retries: 0 })]);
    rerender(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
    await screen.findByTestId("wizard-overall");
    shot("running", second.container);
    click("wizard-cancel");
    shot("cancelled", second.container);
    click("wizard-retry");
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("running"));
    setList([job({ state: "failed", failure: { kind: "network", message: plainText("The server closed the connection") } }), job({ id: "j2", state: "downloading" }), job({ id: "j3", state: "downloading" })]);
    rerender(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("failed"));
    shot("failed", second.container);
    setList([]);
    click("wizard-back");
    await screen.findByTestId("wizard-choose");
    mocks.startMode = "fail";
    click("wizard-start");
    await screen.findByTestId("wizard-error");
    shot("could not start", second.container);
    mocks.startMode = "ok";
    click("wizard-retry");
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("running"));
    setList([job({ state: "failed", failure: null }), job({ id: "j2", state: "downloading" }), job({ id: "j3", state: "downloading" })]);
    rerender(wrap(locale, <Wizard backend={backend} onExit={() => undefined} />));
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("failed"));
    shot("failed, no reason given", second.container);
  },
  "wizard: the self-test": async (shot, locale) => {
    setList([]);
    mocks.selfTestMode = "pending";
    mocks.startMode = "none";
    const view = { ...windowsView(), profiles: windowsView().profiles.map((p) => ({ ...p, missing: [], downloadBytes: 0 })) };
    const { container } = await wizard(locale, view);
    click("wizard-start");
    await screen.findByTestId("wizard-selftest");
    shot("running", container);
    cleanup();
    mocks.selfTestMode = "queue";
    mocks.selfTests = [run({ stages: [stage("asr", true), stage("llm", true)] }), run({ ok: false, stages: [stage("asr", false)], message: plainText("Nothing started") }), undefined];
    const second = await wizard(locale, view);
    click("wizard-start");
    await screen.findByTestId("wizard-result");
    shot("passed", second.container);
    click("wizard-rerun");
    await waitFor(() => expect(screen.getByTestId("wizard-result").textContent).toContain("Nothing started"));
    shot("failed", second.container);
    click("wizard-rerun");
    await waitFor(() => expect(screen.getByTestId("wizard-error")).toBeTruthy());
    shot("no result", second.container);
    mocks.selfTestMode = "reject";
    click("wizard-rerun");
    await waitFor(() => expect(screen.getByTestId("wizard-error").textContent).toContain("crashed"));
    shot("crashed", second.container);
    mocks.selfTestMode = "queue";
    click("wizard-back");
    await screen.findByTestId("wizard-choose");
    shot("back to the profiles", second.container);
  },
  "models: the table with every kind of row": async (shot, locale) => {
    mocks.inventory = richInventory();
    mocks.updates = reportOf();
    const active = job({ assetId: "llama.cpp-b12068-win-cuda", state: "downloading", bytesDone: 100_000_000, bytesTotal: 300_000_000, speedBps: 3_000_000 });
    const downloads = { list: [active], byAsset: new Map([[active.assetId, active]]), refresh: () => undefined };
    const { container } = render(wrap(locale, <ModelsSection backend={backend} downloads={downloads} />));
    await screen.findByTestId("inv-table");
    shot("every row", container);
    click("check-updates");
    await screen.findByTestId("update-message");
    await waitFor(() => expect(screen.getByTestId("inv-whisper-large-v3-turbo-update")).toBeTruthy());
    shot("after the update check", container);
  },
  "models: the loading and failing states": async (shot, locale) => {
    mocks.inventoryMode = "pending";
    const first = render(wrap(locale, <ModelsSection backend={backend} downloads={{ list: [], byAsset: new Map(), refresh: () => undefined }} />));
    shot("loading", first.container);
    first.unmount();
    mocks.inventoryMode = "fail";
    const second = render(wrap(locale, <ModelsSection backend={backend} downloads={{ list: [], byAsset: new Map(), refresh: () => undefined }} />));
    await screen.findByTestId("inv-error");
    shot("could not read", second.container);
    second.unmount();
    mocks.inventoryMode = "ok";
    mocks.inventory = windowsInventory();
    mocks.updatesMode = "fail";
    const third = render(wrap(locale, <ModelsSection backend={backend} downloads={{ list: [], byAsset: new Map(), refresh: () => undefined }} />));
    await screen.findByTestId("inv-table");
    click("check-updates");
    await screen.findByTestId("inv-error");
    shot("update check failed", third.container);
  },
  "models: the row actions": async (shot, locale) => {
    mocks.inventory = richInventory();
    mocks.verifiedInventory = { ...richInventory(), assets: richInventory().assets.map((a) => (a.id === "qwen3-8b-q4_k_m" ? { ...a, shaState: "verified" } : a)) };
    const downloads = { list: [], byAsset: new Map(), refresh: () => undefined };
    const { container } = render(wrap(locale, <ModelsSection backend={backend} downloads={downloads} />));
    await screen.findByTestId("inv-table");
    mocks.action = "refuse";
    click("act-qwen3-8b-q4_k_m-verify");
    await waitFor(() => expect(screen.getByTestId("inv-qwen3-8b-q4_k_m-note").textContent).toContain("SHA256"));
    shot("verified, still corrupt", container);
    mocks.action = "ok";
    mocks.verifiedInventory = null;
    click("act-qwen3-8b-q4_k_m-repair");
    await waitFor(() => expect(screen.getByTestId("inv-qwen3-8b-q4_k_m-note").textContent).toContain("redownload"));
    shot("repaired, with a reason", container);
    mocks.repair = { action: "none", reason: "", job: null };
    click("act-qwen3-8b-q4_k_m-repair");
    await waitFor(() => expect(screen.getByTestId("inv-qwen3-8b-q4_k_m-note").textContent).toContain("none"));
    shot("repaired, no reason", container);
    mocks.action = "refuse";
    click("act-qwen3-8b-q4_k_m-redownload");
    await waitFor(() => expect(screen.getByTestId("inv-qwen3-8b-q4_k_m-note").textContent).toContain("Another download"));
    shot("refused", container);
    mocks.action = "pending";
    click("act-qwen3-8b-q4_k_m-redownload");
    shot("working", container);
  },
  "models: the delete dialog": async (shot, locale) => {
    const asset0 = richInventory().assets[0] as Asset;
    const bare = asset("loose-model", "model", { state: "installed", path: null, sizeOnDisk: null });
    const open = (a: Asset) => render(wrap(locale, <DeleteDialog backend={backend} asset={a} onClose={() => undefined} onDeleted={() => undefined} />));
    const first = open(asset0);
    shot("confirm with a warning", first.container);
    mocks.deleteMode = "refuse-force";
    click("delete-confirm");
    await screen.findByTestId("delete-refused");
    shot("refused, force allowed", first.container);
    click("delete-want-force");
    await screen.findByTestId("delete-force");
    shot("force, no reason yet", first.container);
    typeInto("force-reason", "short");
    shot("force, reason too short", first.container);
    typeInto("force-reason", "replace it with a new download");
    shot("force, reason ready", first.container);
    click("force-confirm");
    await screen.findByTestId("delete-failed");
    shot("force failed", first.container);
    first.unmount();
    mocks.deleteMode = "refuse-plain";
    const second = open({ ...asset0, blockers: [], sizeOnDisk: 1_500_000 });
    shot("confirm, plain", second.container);
    click("delete-confirm");
    await screen.findByTestId("delete-failed");
    shot("refused with nothing to force", second.container);
    second.unmount();
    mocks.deleteMode = "refuse";
    const third = open({ ...bare, path: "C:/m/x.bin" });
    shot("confirm, no size", third.container);
    click("delete-confirm");
    await screen.findByTestId("delete-refused");
    shot("refused, cannot force", third.container);
    third.unmount();
    const fourth = open(bare);
    shot("confirm, no size and no path", fourth.container);
  },
  "models: the models folder": async (shot, locale) => {
    mocks.inventory = richInventory();
    mocks.settings = settingsView();
    const changed = vi.fn();
    const { container } = render(wrap(locale, <StorageCard backend={backend} onChanged={changed} />));
    await waitFor(() => expect(screen.getByTestId("models-dir").textContent).toBe("C:/m"));
    shot("default folder", container);
    typeInto("models-dir-input", "E:/vst-models");
    click("models-dir-change");
    await screen.findByTestId("models-dir-confirm");
    shot("confirm", container);
    mocks.setDirMode = "fail";
    click("models-dir-only");
    await screen.findByTestId("models-dir-error");
    shot("could not change", container);
    mocks.setDirMode = "ok";
    typeInto("models-dir-input", "E:/vst-models");
    click("models-dir-change");
    await screen.findByTestId("models-dir-confirm");
    click("models-dir-only");
    await screen.findByTestId("models-dir-warning");
    shot("changed, with a warning", container);
    typeInto("models-dir-input", "E:/vst-models");
    click("models-dir-change");
    await screen.findByTestId("models-dir-confirm");
    click("models-dir-cancel");
    shot("cancelled", container);
    mocks.picked = "F:/picked";
    click("models-dir-pick");
    await waitFor(() => expect((screen.getByTestId("models-dir-input") as HTMLInputElement).value).toBe("F:/picked"));
    mocks.picked = null;
  },
  "models: a custom folder and the move": async (shot, locale) => {
    mocks.inventory = richInventory();
    mocks.settings = settingsView("D:/models", "D:/models");
    const states: Record<string, Partial<MoveStatus>> = {
      running: { state: "running", target: "F:/new", filesTotal: 3, filesDone: 1, bytesTotal: 2_000_000_000, bytesDone: 500_000_000, warnings: ["Antivirus may slow this down"] },
      done: { state: "done", target: "F:/new", filesTotal: 3, filesDone: 3, bytesTotal: 2_000_000_000, bytesDone: 2_000_000_000 },
      "done, one file": { state: "done", target: "F:/new", filesTotal: 1, filesDone: 1, bytesTotal: 1_000_000, bytesDone: 1_000_000 },
      failed: { state: "failed", target: "F:/new", filesTotal: 3, filesDone: 1, error: "Not enough space on F:" },
      "failed, no reason": { state: "failed", target: "F:/new", filesTotal: 3, filesDone: 1, error: null },
    };
    for (const [name, over] of Object.entries(states)) {
      mocks.move = { state: "idle", target: null, filesTotal: 0, filesDone: 0, bytesTotal: 0, bytesDone: 0, error: null, warnings: [], ...over };
      const { container, unmount } = render(wrap(locale, <StorageCard backend={backend} onChanged={() => undefined} />));
      await waitFor(() => expect(screen.getByTestId("models-dir").textContent).toBe("D:/models"));
      if (over.state === "running" || over.state === "idle") await screen.findByTestId("move-status");
      shot(name, container);
      unmount();
    }
    mocks.move = { state: "idle", target: null, filesTotal: 0, filesDone: 0, bytesTotal: 0, bytesDone: 0, error: null, warnings: [] };
    const { container } = render(wrap(locale, <StorageCard backend={backend} onChanged={() => undefined} />));
    await waitFor(() => expect(screen.getByTestId("models-dir").textContent).toBe("D:/models"));
    typeInto("models-dir-input", "F:/new");
    click("models-dir-change");
    await screen.findByTestId("models-dir-confirm");
    mocks.moveStartMode = "fail";
    click("models-dir-move");
    await screen.findByTestId("models-dir-error");
    shot("move could not start", container);
    mocks.moveStartMode = "ok";
    typeInto("models-dir-input", "F:/new");
    click("models-dir-change");
    await screen.findByTestId("models-dir-confirm");
    click("models-dir-move");
    await screen.findByTestId("move-status");
    shot("move started", container);
  },
  "models: the page as the settings page frames it": async (shot, locale) => {
    mocks.inventory = windowsInventory();
    mocks.settings = settingsView();
    const { container } = render(wrap(locale, <SettingsPageAlone backend={backend} initial="models" />));
    await screen.findByTestId("inv-table");
    await waitFor(() => expect(screen.getByTestId("models-dir").textContent).toBe("C:/m"));
    shot("models page", container);
  },
  "models: a Mac with a local build": async (shot, locale) => {
    mocks.inventory = macInventory();
    mocks.settings = settingsView("/Users/me/models");
    const { container } = render(wrap(locale, <SettingsPageAlone backend={backend} initial="models" />));
    await screen.findByTestId("inv-table");
    shot("mac models", container.querySelector("[data-testid='inv-table']") as Element);
  },
};

beforeEach(() => {
  localStorage.clear();
  mocks.profileMode = "ok";
  mocks.chooseMode = "ok";
  mocks.startMode = "ok";
  mocks.selfTestMode = "queue";
  mocks.selfTests = [];
  mocks.dl = { list: [], byAsset: new Map(), refresh: () => undefined };
  mocks.inventoryMode = "ok";
  mocks.updatesMode = "ok";
  mocks.action = "ok";
  mocks.verifiedInventory = null;
  mocks.repair = { action: "redownload", reason: "SHA256 mismatch", job: null };
  mocks.deleteMode = "ok";
  mocks.setDirMode = "ok";
  mocks.moveStartMode = "ok";
  mocks.picked = null;
  mocks.move = { state: "idle", target: null, filesTotal: 0, filesDone: 0, bytesTotal: 0, bytesDone: 0, error: null, warnings: [] };
  mocks.settings = settingsView();
  mocks.updates = reportOf();
  mocks.inventory = windowsInventory();
});
afterEach(async () => {
  await act(async () => undefined);
  cleanup();
});

describe.each(["zh-TW", "en"] as const)("W2 screens in %s", (locale) => {
  for (const [name, screenFn] of Object.entries(SCREENS)) {
    it(name, async () => {
      const seen: Record<string, Harvest> = {};
      const shot: Shot = (label, root) => {
        seen[label] = harvest(root ?? document.body);
      };
      await screenFn(shot, locale);
      expect(Object.keys(seen).length).toBeGreaterThan(0);
      if (locale === "en") {
        for (const [label, h] of Object.entries(seen)) {
          expect(NOT_ENGLISH.test(h.text), `${name} / ${label}: ${h.text}`).toBe(false);
          for (const a of h.attrs) expect(NOT_ENGLISH.test(a), `${name} / ${label}: ${a}`).toBe(false);
        }
        return;
      }
      if (WRITE) {
        written[name] = [seen as never];
        return;
      }
      const fixture = JSON.parse((await files()).readFileSync(FIXTURE, "utf-8")) as Record<string, [Record<string, Harvest>]>;
      expect(Object.keys(seen), name).toEqual(Object.keys(fixture[name]![0]!));
      for (const [label, h] of Object.entries(seen)) {
        const old = fixture[name]![0]![label]!;
        expect(h.text, `${name} / ${label}`).toBe(old.text);
        expect(h.attrs, `${name} / ${label}`).toEqual(old.attrs);
      }
    });
  }
});

afterAll(async () => {
  if (WRITE) (await files()).writeFileSync(FIXTURE, `${JSON.stringify(written, null, 1)}\n`, "utf-8");
});
