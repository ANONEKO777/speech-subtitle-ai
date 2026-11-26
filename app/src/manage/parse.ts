import { ApiError, asRecord } from "../api/client";
import { DEFAULT_UI_LANGUAGE, isUiLanguage } from "../i18n/locale";
import type {
  Asset,
  DownloadJob,
  Hardware,
  Inventory,
  JobState,
  LicenseEntry,
  LlmSaved,
  LlmSource,
  LlmTest,
  MissingAsset,
  MoveState,
  MoveStatus,
  ProfileId,
  ProfileOption,
  ProfileView,
  SelfTest,
  SettingsView,
  StageResult,
  UpdateItem,
  UpdateReport,
} from "./types";
import { PROFILE_IDS } from "./types";
import { saidField } from "../i18n/said";

type Rec = Record<string, unknown>;

const rec = (v: unknown): Rec => asRecord(v) ?? {};
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const str = (o: Rec, k: string, d = ""): string => (typeof o[k] === "string" ? o[k] : d);
const strOrNull = (o: Rec, k: string): string | null => (typeof o[k] === "string" ? o[k] : null);
const num = (o: Rec, k: string, d = 0): number => (typeof o[k] === "number" ? o[k] : d);
const numOrNull = (o: Rec, k: string): number | null => (typeof o[k] === "number" ? o[k] : null);
const bool = (o: Rec, k: string): boolean => o[k] === true;
const strings = (v: unknown): string[] => list(v).filter((x): x is string => typeof x === "string");
const oneOf = <T extends string>(v: unknown, all: readonly T[], what: string): T => {
  const found = all.find((a) => a === v);
  if (found === undefined) throw new ApiError(500, `unexpected ${what} ${String(v)}`);
  return found;
};

const STATES = ["not_installed", "partial", "installing", "installed"] as const;
const SHA = ["verified", "unchecked", "corrupt", "not_installed"] as const;
const JOB_STATES: readonly JobState[] = ["queued", "downloading", "verifying", "extracting", "done", "failed", "cancelled"];
const SOURCES: readonly LlmSource[] = ["builtin", "ollama", "cloud"];

export function parseAsset(raw: unknown): Asset {
  const o = rec(raw);
  return {
    id: str(o, "id"),
    type: o["type"] === "runtime" ? "runtime" : "model",
    kind: str(o, "kind"),
    state: oneOf(o["state"], STATES, "state"),
    version: str(o, "version"),
    installedVersion: strOrNull(o, "installed_version"),
    sizeBytes: num(o, "size_bytes"),
    sizeOnDisk: numOrNull(o, "size_on_disk"),
    path: strOrNull(o, "path"),
    shaState: oneOf(o["sha256_state"], SHA, "sha256_state"),
    shaScope: o["sha256_scope"] === "archive_at_install" ? "archive_at_install" : "file",
    usedByProfiles: strings(o["used_by_profiles"]),
    inActiveProfile: bool(o, "in_active_profile"),
    dependents: list(o["dependents"]).map((d) => ({ id: str(rec(d), "id"), installed: bool(rec(d), "installed") })),
    blockers: strings(o["blockers"]),
    license: str(o, "license"),
    licenseUrl: str(o, "license_url"),
    localBuild: bool(o, "local_build"),
    foundOutsideRuntimes: bool(o, "found_outside_runtimes"),
  };
}

export function parseInventory(raw: unknown): Inventory {
  const o = rec(raw);
  return {
    activeProfile: str(o, "active_profile"),
    modelsDir: str(o, "models_dir"),
    runtimesDir: str(o, "runtimes_dir"),
    installedBytes: num(o, "installed_bytes"),
    assets: list(o["assets"]).map(parseAsset),
  };
}

export function parseJob(raw: unknown): DownloadJob {
  const o = rec(raw);
  const f = asRecord(o["failure"]);
  return {
    id: str(o, "id"),
    assetId: str(o, "asset_id"),
    state: oneOf(o["state"], JOB_STATES, "download state"),
    bytesDone: num(o, "bytes_done"),
    bytesTotal: num(o, "bytes_total"),
    speedBps: num(o, "speed_bps"),
    resumedFrom: num(o, "resumed_from"),
    retries: num(o, "retries"),
    note: strOrNull(o, "note"),
    failure: f ? { kind: str(f, "kind"), message: str(f, "message") } : null,
  };
}

function parseHardware(raw: unknown): Hardware {
  const o = rec(raw);
  return {
    platform: str(o, "platform"),
    chip: strOrNull(o, "chip"),
    gpuName: strOrNull(o, "gpu_name"),
    vramMib: numOrNull(o, "vram_mib"),
    driverVersion: strOrNull(o, "driver_version"),
    ramMib: numOrNull(o, "ram_mib"),
    diskFreeMib: numOrNull(o, "disk_free_mib"),
  };
}

const missing = (raw: unknown): MissingAsset => {
  const o = rec(raw);
  return { id: str(o, "id"), type: str(o, "type"), sizeBytes: num(o, "size_bytes"), localBuild: bool(o, "local_build") };
};

function parseOption(raw: unknown): ProfileOption {
  const o = rec(raw);
  return {
    id: oneOf(o["id"], PROFILE_IDS, "profile"),
    label: str(o, "label"),
    recommendCloud: bool(o, "recommend_cloud"),
    fitsHardware: bool(o, "fits_hardware"),
    active: bool(o, "active"),
    recommended: bool(o, "recommended"),
    missing: list(o["missing"]).map(missing),
    downloadBytes: num(o, "download_bytes"),
    asrModel: str(rec(o["asr"]), "model"),
    llmModel: str(rec(o["llm"]), "model"),
  };
}

export function parseProfileView(raw: unknown): ProfileView {
  const o = rec(raw);
  const rcm = rec(o["recommended"]);
  const act = rec(o["active"]);
  const fb = asRecord(o["fallback"]);
  return {
    hardware: parseHardware(o["hardware"]),
    vcRuntimeMissing: o["vc_runtime_missing"] === true,
    recommended: { id: oneOf(rcm["id"], PROFILE_IDS, "profile"), label: str(rcm, "label"), why: str(rcm, "why") },
    active: {
      id: oneOf(act["id"], PROFILE_IDS, "profile"),
      label: str(act, "label"),
      source: act["source"] === "user" ? "user" : "recommended",
      device: str(act, "device"),
    },
    profiles: list(o["profiles"]).map(parseOption),
    fallback: fb ? { reason: saidField(fb, "reason") } : null,
  };
}

const stage = (raw: unknown): StageResult => {
  const o = rec(raw);
  return {
    stage: str(o, "stage"),
    runtimeId: str(o, "runtime_id"),
    device: str(o, "device"),
    installed: bool(o, "installed"),
    ok: bool(o, "ok"),
    seconds: num(o, "seconds"),
    detail: saidField(o, "detail"),
  };
};

export function parseSelfTest(raw: unknown): SelfTest | null {
  const o = asRecord(raw);
  if (!o) return null;
  const fb = asRecord(o["fallback"]);
  return {
    ok: bool(o, "ok"),
    device: str(o, "device"),
    stages: list(o["stages"]).map(stage),
    fallback: fb ? { reason: saidField(fb, "reason") } : null,
    seconds: num(o, "seconds"),
    message: saidField(o, "message"),
  };
}

export function parseSettings(raw: unknown): SettingsView {
  const o = rec(raw);
  const l = rec(o["llm"]);
  const llm: LlmSaved = {
    source: oneOf(l["source"] ?? "builtin", SOURCES, "llm source"),
    ollamaUrl: str(l, "ollama_url"),
    ollamaModel: str(l, "ollama_model"),
    cloudUrl: str(l, "cloud_url"),
    cloudModel: str(l, "cloud_model"),
    cloudConsent: bool(l, "cloud_consent"),
    apiKeySet: bool(l, "api_key_set"),
  };
  const s = rec(o["storage"]);
  return {
    uiLanguage: isUiLanguage(o["ui_language"]) ? o["ui_language"] : DEFAULT_UI_LANGUAGE,
    llm,
    consentText: str(o, "cloud_consent_text"),
    problem: strOrNull(o, "problem"),
    storage: { userData: str(s, "user_data"), modelsDir: str(s, "models_dir"), customModelsDir: strOrNull(s, "custom_models_dir") },
  };
}

export const parseLlmTest = (raw: unknown): LlmTest => {
  const o = rec(raw);
  return { ok: bool(o, "ok"), url: str(o, "url"), detail: saidField(o, "detail"), models: strings(o["models"]) };
};

const updateItem = (raw: unknown): UpdateItem => {
  const o = rec(raw);
  const status = o["status"];
  return {
    id: str(o, "id"),
    status: status === "not_installed" || status === "current" || status === "update_available" ? status : "unknown",
    installable: bool(o, "installable"),
    message: str(o, "message"),
  };
};

export const parseUpdates = (raw: unknown): UpdateReport => {
  const o = rec(raw);
  return { message: str(o, "message"), items: list(o["items"]).map(updateItem) };
};

export const parseLicenses = (raw: unknown): LicenseEntry[] =>
  list(rec(raw)["licenses"]).map((item) => {
    const o = rec(item);
    return {
      id: str(o, "id"),
      type: str(o, "type"),
      version: str(o, "version"),
      license: str(o, "license"),
      licenseUrl: str(o, "license_url"),
      parts: list(o["parts"]).map((p) => ({ id: str(rec(p), "id"), url: str(rec(p), "url") })),
      sourceUrl: str(o, "source_url"),
    };
  });

const MOVE: readonly MoveState[] = ["idle", "running", "done", "failed"];

export const parseMove = (raw: unknown): MoveStatus => {
  const o = rec(raw);
  return {
    state: oneOf(o["state"], MOVE, "move state"),
    target: strOrNull(o, "target"),
    filesTotal: num(o, "files_total"),
    filesDone: num(o, "files_done"),
    bytesTotal: num(o, "bytes_total"),
    bytesDone: num(o, "bytes_done"),
    error: strOrNull(o, "error"),
    warnings: strings(o["warnings"]),
  };
};

export const asProfileId = (id: string): ProfileId | null => PROFILE_IDS.find((p) => p === id) ?? null;
