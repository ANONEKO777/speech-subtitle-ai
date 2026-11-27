// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { JobRow } from "../manage/JobRow";
import { parseJob, parseUpdates } from "../manage/parse";
import { windowsInventory, windowsView } from "../manage/screens.fixture";
import type { DownloadJob, ProfileView } from "../manage/types";
import { ModelsSection } from "../models-page/ModelsSection";
import { HardwareSection } from "../settings/HardwareSection";
import { Wizard } from "../wizard/Wizard";
import { I18nProvider, useI18n } from "./I18nProvider";
import type { Locale } from "./locale";
import { parseNotices } from "./notice";
import fixture from "./notices.w4b.fixture.json";

/**
 * The places this round added to the wording: the "why" box of the hardware page, the update check
 * of the models page, and a failed download in a job row, in the models table and in the wizard.
 * Each shows a backend scenario in the window's language, and again after a change of language.
 */

const mocks = vi.hoisted(() => ({
  profile: null as unknown,
  updates: null as unknown,
  inventory: null as unknown,
  downloads: { list: [] as unknown[], byAsset: new Map<string, unknown>(), refresh: () => undefined },
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: () => Promise.resolve(null) }));
vi.mock("../manage/useDownloads", () => ({ useDownloads: () => mocks.downloads }));
vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: () => Promise.resolve(mocks.profile),
  fetchLastSelfTest: () => Promise.resolve(null),
  fetchLicenses: () => Promise.resolve([]),
  fetchInventory: () => Promise.resolve(mocks.inventory),
  checkUpdates: () => Promise.resolve(mocks.updates),
  chooseProfile: () => Promise.resolve({ profile: mocks.profile, warnings: [] }),
  downloadProfileAssets: () => Promise.resolve([{ id: "j1" }]),
  startAsset: () => Promise.resolve({ id: "j1" }),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const backend = { port: 1, token: "t" } as Backend;
const scenario = (name: keyof typeof fixture) => fixture[name];

let change: (locale: Locale) => void = () => undefined;
function Switch({ children }: { children: ReactNode }) {
  const i18n = useI18n()!;
  change = i18n.setUiLanguage;
  return <>{children}</>;
}
const wrap = (node: ReactNode) => (
  <I18nProvider initial="zh-TW">
    <Switch>{node}</Switch>
  </I18nProvider>
);
const switchTo = (locale: Locale) => act(() => change(locale));

/** Both languages of what `read` finds: Traditional Chinese first, then English after a change. */
function bothLanguages(read: () => string | null | undefined, zh: string, en: string): void {
  expect(read()).toContain(zh);
  switchTo("en");
  expect(read()).toContain(en);
  expect(read()).not.toContain(zh);
}

const WHY = scenario("why.fallbackBlocked");

describe("why a profile was chosen", () => {
  it("words each line of the box on the hardware page", async () => {
    const view: ProfileView = { ...windowsView(), recommended: { id: "gpu-24gb", label: "24 GB", why: { text: WHY.text, notices: parseNotices(WHY.notices) } } };
    mocks.profile = view;
    render(wrap(<HardwareSection backend={backend} downloads={mocks.downloads as never} onOpenLlm={() => undefined} />));
    const box = await waitFor(() => {
      const found = document.querySelector("pre.why");
      if (!found) throw new Error("not shown yet");
      return found;
    });

    bothLanguages(() => box.textContent, WHY.zh, WHY.before);
  });
});

const SUMMARY = scenario("updates.available");
const ITEM = scenario("updates.item.unrecorded");

describe("the update check on the models page", () => {
  it("words the summary line and the tooltip of a row", async () => {
    mocks.inventory = windowsInventory();
    mocks.updates = parseUpdates({
      message: SUMMARY.text,
      message_notices: SUMMARY.notices,
      items: [{ id: "whisper-large-v3-turbo", status: "unknown", installable: true, message: ITEM.text, message_notices: ITEM.notices }],
    });
    render(wrap(<ModelsSection backend={backend} downloads={mocks.downloads as never} />));
    await waitFor(() => screen.getByTestId("inv-table"));
    fireEvent.click(screen.getByTestId("check-updates"));
    const line = await waitFor(() => screen.getByTestId("update-message"));
    const row = screen.getByTestId("inv-whisper-large-v3-turbo-update");

    expect(line.textContent).toBe(SUMMARY.zh);
    expect(row.getAttribute("title")).toBe(ITEM.zh);
    switchTo("en");
    expect(line.textContent).toBe(SUMMARY.before);
    expect(row.getAttribute("title")).toBe(ITEM.before);
  });
});

const LOCKED = scenario("download.lockedMoving");
const INTERRUPTED = scenario("download.rangeRefused");

const failedJob = (assetId: string, failed: { text: string; notices: unknown }): DownloadJob =>
  parseJob({ id: "j1", asset_id: assetId, state: "failed", bytes_done: 0, bytes_total: 10, speed_bps: 0, resumed_from: 0, retries: 0, note: null, failure: { kind: "io", message: failed.text, message_notices: failed.notices } });

describe("a download that failed", () => {
  it("words the reason in a job row, with the sentence it quotes", () => {
    render(wrap(<JobRow job={failedJob("a", INTERRUPTED)} testId="job" />));

    bothLanguages(() => screen.getByTestId("job-error").textContent, INTERRUPTED.zh, INTERRUPTED.before);
  });

  it("words the reason in the models table", async () => {
    const id = "whisper-large-v3-turbo";
    const job = failedJob(id, LOCKED);
    mocks.inventory = windowsInventory();
    render(wrap(<ModelsSection backend={backend} downloads={{ ...mocks.downloads, list: [job], byAsset: new Map([[id, job]]) } as never} />));
    const note = await waitFor(() => screen.getByTestId(`inv-${id}-note`));

    bothLanguages(() => note.textContent, LOCKED.zh, LOCKED.before);
  });

  it("words the reason inside the wizard's own sentence", async () => {
    mocks.profile = windowsView();
    const shown = () => wrap(<Wizard backend={backend} onExit={() => undefined} />);
    const { rerender } = render(shown());
    await waitFor(() => screen.getByTestId("wizard-choose"));
    fireEvent.click(screen.getByTestId("wizard-start"));
    await waitFor(() => expect(screen.getByTestId("wizard-download").getAttribute("data-phase")).toBe("running"));
    const job = failedJob("whisper-large-v3-turbo", LOCKED);
    mocks.downloads = { ...mocks.downloads, list: [job], byAsset: new Map([[job.assetId, job]]) };
    rerender(shown());
    const error = await waitFor(() => screen.getByTestId("wizard-error"));

    bothLanguages(() => error.textContent, LOCKED.zh, LOCKED.before);
  });
});
