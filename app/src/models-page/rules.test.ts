import { describe, expect, it } from "vitest";
import type { Asset, DownloadJob } from "../manage/types";
import { tZhTW } from "../i18n";
import { forceReasonError, reduceDelete, rowActions, shaText } from "./rules";
import { plainText } from "../i18n/said";

const asset = (over: Partial<Asset> = {}): Asset => ({
  id: "whisper",
  type: "model",
  kind: "asr",
  state: "installed",
  version: "1",
  installedVersion: "1",
  sizeBytes: 10,
  sizeOnDisk: 10,
  path: "C:/m",
  shaState: "verified",
  shaScope: "file",
  usedByProfiles: [],
  inActiveProfile: false,
  dependents: [],
  blockers: [],
  license: "MIT",
  licenseUrl: "https://x",
  localBuild: false,
  foundOutsideRuntimes: false,
  ...over,
});
const job = (state: DownloadJob["state"]): DownloadJob => ({
  id: "j",
  assetId: "whisper",
  state,
  bytesDone: 0,
  bytesTotal: 1,
  speedBps: 0,
  resumedFrom: 0,
  retries: 0,
  note: null,
  failure: null,
});

describe("row actions", () => {
  it("offers verify only for a model, because a runtime's archive was hashed at install", () => {
    expect(rowActions(asset(), undefined)).toEqual(["verify", "repair", "redownload", "delete"]);
    expect(rowActions(asset({ type: "runtime" }), undefined)).toEqual(["repair", "redownload", "delete"]);
  });

  it("offers a download for a missing asset and a resume for a half download", () => {
    expect(rowActions(asset({ state: "not_installed" }), undefined)).toEqual(["download"]);
    expect(rowActions(asset({ state: "partial" }), job("cancelled"))).toEqual(["resume", "delete"]);
  });

  it("offers no download for a program this machine builds, and only delete once it is there", () => {
    const built = { type: "runtime", localBuild: true } as const;
    expect(rowActions(asset({ ...built, state: "not_installed" }), undefined)).toEqual([]);
    expect(rowActions(asset({ ...built, state: "installed" }), undefined)).toEqual(["delete"]);
    expect(rowActions(asset({ type: "runtime", state: "not_installed" }), undefined)).toEqual(["download"]);
  });

  it("offers nothing for a program found on PATH or in Homebrew, because the app will not delete it", () => {
    expect(rowActions(asset({ type: "runtime", localBuild: true, foundOutsideRuntimes: true, state: "installed" }), undefined)).toEqual([]);
  });

  it("offers only cancel while a job runs", () => {
    expect(rowActions(asset({ state: "not_installed" }), job("downloading"))).toEqual(["cancel"]);
  });

  it("offers an update only when the backend can install it", () => {
    const update = { id: "whisper", status: "update_available", installable: true, message: "" } as const;
    expect(rowActions(asset(), undefined, update)[0]).toBe("update");
    expect(rowActions(asset(), undefined, { ...update, installable: false })).not.toContain("update");
  });
});

describe("delete flow", () => {
  const refusal = { message: plainText("needed"), blockers: ["the active profile needs it"], canForce: true };

  it("shows the blockers and lets the person force with a reason", () => {
    let s = reduceDelete({ step: "confirm" }, { type: "refused", refusal });
    expect(s).toEqual({ step: "refused", refusal });
    s = reduceDelete(s, { type: "wantForce" });
    s = reduceDelete(s, { type: "reason", text: "short" });
    expect(s).toEqual({ step: "force", refusal, reason: "short" });
    expect(forceReasonError("short", tZhTW)).not.toBeNull();
    expect(forceReasonError("  reinstalling it  ", tZhTW)).toBeNull();
  });

  it("offers no force when the backend does not", () => {
    const locked = { message: plainText("C:/m/a.bin is in use. Close the program that holds it."), blockers: [], canForce: false };
    expect(reduceDelete({ step: "confirm" }, { type: "refused", refusal: locked })).toEqual({ step: "failed", message: locked.message });
    const noForce = { message: plainText("x"), blockers: ["b"], canForce: false };
    const s = reduceDelete({ step: "confirm" }, { type: "refused", refusal: noForce });
    expect(reduceDelete(s, { type: "wantForce" })).toBe(s);
  });
});

describe("sha text", () => {
  it("says a runtime was verified at install", () => {
    expect(shaText(asset({ type: "runtime", shaScope: "archive_at_install" }), tZhTW)).toBe("安裝時已驗證");
    expect(shaText(asset({ shaState: "corrupt" }), tZhTW)).toBe("SHA256 不符");
  });
});
