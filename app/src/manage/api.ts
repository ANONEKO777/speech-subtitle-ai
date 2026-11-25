import { invoke } from "@tauri-apps/api/core";
import { ApiError, type Backend, asRecord, call } from "../api/client";
import type { UiLanguage } from "../i18n/locale";
import {
  parseInventory,
  parseJob,
  parseLicenses,
  parseLlmTest,
  parseMove,
  parseProfileView,
  parseSelfTest,
  parseSettings,
  parseUpdates,
} from "./parse";
import type { Asset, DownloadJob, Inventory, LlmSource, ProfileId } from "./types";

const seg = encodeURIComponent;
const post = (b: Backend, path: string, body?: unknown) =>
  call(b, path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
const put = (b: Backend, path: string, body: unknown) => call(b, path, { method: "PUT", body: JSON.stringify(body) });

export const fetchInventory = async (b: Backend): Promise<Inventory> => parseInventory(await call(b, "/api/inventory"));
export const fetchProfile = async (b: Backend) => parseProfileView(await call(b, "/api/profile"));
export const fetchSettings = async (b: Backend) => parseSettings(await call(b, "/api/settings"));
export const fetchLicenses = async (b: Backend) => parseLicenses(await call(b, "/api/licenses"));
export const fetchLastSelfTest = async (b: Backend) => parseSelfTest(await call(b, "/api/runtimes/selftest"));
export const runSelfTest = async (b: Backend) => parseSelfTest(await post(b, "/api/runtimes/selftest"));
export const checkUpdates = async (b: Backend) => parseUpdates(await post(b, "/api/updates/check"));

/** The kind and install state of every model. Cheap: no hardware probe, so the app can ask at start. */
export async function fetchModelStates(b: Backend): Promise<{ kind: string; state: string }[]> {
  const models = asRecord(await call(b, "/api/registry"))?.["models"];
  return (Array.isArray(models) ? models : []).flatMap((m) => {
    const o = asRecord(m);
    return typeof o?.["kind"] === "string" && typeof o["state"] === "string" ? [{ kind: o["kind"], state: o["state"] }] : [];
  });
}

export async function fetchDownloads(b: Backend): Promise<DownloadJob[]> {
  const body = await call(b, "/api/downloads");
  return Array.isArray(body) ? body.map(parseJob) : [];
}

export const cancelDownload = (b: Backend, jobId: string) => post(b, `/api/downloads/${seg(jobId)}/cancel`);

/** Starts, or resumes from the `.part` file, the download of one asset. */
export async function startAsset(b: Backend, asset: Pick<Asset, "id" | "type">): Promise<DownloadJob> {
  const path = asset.type === "model" ? `/api/models/${seg(asset.id)}/download` : `/api/runtimes/${seg(asset.id)}/install`;
  return parseJob(await post(b, path));
}

export async function redownload(b: Backend, id: string): Promise<DownloadJob> {
  return parseJob(await post(b, `/api/inventory/${seg(id)}/redownload`));
}

export async function updateAsset(b: Backend, id: string): Promise<DownloadJob> {
  return parseJob(await post(b, `/api/inventory/${seg(id)}/update`));
}

export interface Repair {
  readonly action: string;
  readonly reason: string;
  readonly job: DownloadJob | null;
}

export async function repairAsset(b: Backend, id: string): Promise<Repair> {
  const o = asRecord(await post(b, `/api/inventory/${seg(id)}/repair`));
  const job = asRecord(o?.["job"]);
  return {
    action: typeof o?.["action"] === "string" ? o["action"] : "",
    reason: typeof o?.["reason"] === "string" ? o["reason"] : "",
    job: job ? parseJob(job) : null,
  };
}

export const verifyAsset = (b: Backend, id: string) => post(b, `/api/inventory/${seg(id)}/verify`);

export async function deleteAsset(b: Backend, asset: Pick<Asset, "id" | "type">, force?: { readonly reason: string }): Promise<void> {
  const kind = asset.type === "model" ? "models" : "runtimes";
  const query = force ? `?force=true&reason=${seg(force.reason)}` : "";
  await call(b, `/api/${kind}/${seg(asset.id)}${query}`, { method: "DELETE" });
}

/** Why a delete or another action was refused: the message, the blockers and whether force is offered. */
export interface Refusal {
  readonly message: string;
  readonly blockers: readonly string[];
  readonly canForce: boolean;
}

export function refusalOf(e: unknown): Refusal {
  if (!(e instanceof ApiError)) return { message: e instanceof Error ? e.message : String(e), blockers: [], canForce: false };
  const d = asRecord(e.detail);
  const blockers = Array.isArray(d?.["blockers"]) ? d["blockers"].filter((x): x is string => typeof x === "string") : [];
  return { message: e.message, blockers, canForce: d?.["can_force"] === true };
}

export interface ProfileChange {
  readonly warnings: readonly string[];
  readonly profile: Awaited<ReturnType<typeof fetchProfile>>;
}

/** Switches the active profile; `null` follows the recommendation for the detected hardware. */
export async function chooseProfile(b: Backend, profile: ProfileId | null): Promise<ProfileChange> {
  const body = await put(b, "/api/profile", { profile });
  const warnings = asRecord(body)?.["warnings"];
  return {
    profile: parseProfileView(body),
    warnings: Array.isArray(warnings) ? warnings.filter((w): w is string => typeof w === "string") : [],
  };
}

export async function downloadProfileAssets(b: Backend): Promise<DownloadJob[]> {
  const jobs = asRecord(await post(b, "/api/profile/download"))?.["jobs"];
  return Array.isArray(jobs) ? jobs.map(parseJob) : [];
}

export interface LlmBody {
  readonly source: LlmSource;
  readonly ollama_url: string;
  readonly ollama_model: string;
  readonly cloud_url: string;
  readonly cloud_model: string;
  readonly cloud_consent: boolean;
  /** Omit to keep the saved key, empty to delete it. */
  readonly api_key?: string;
}

export const saveUiLanguage = async (b: Backend, uiLanguage: UiLanguage) =>
  parseSettings(await put(b, "/api/settings", { ui_language: uiLanguage }));
export const saveLlm = async (b: Backend, llm: LlmBody) => parseSettings(await put(b, "/api/settings", { llm }));
export const testLlm = async (b: Backend, llm: LlmBody) => parseLlmTest(await post(b, "/api/llm/test", { llm }));

export interface StorageChange {
  readonly warnings: readonly string[];
}

export async function setModelsDir(b: Backend, dir: string | null): Promise<StorageChange> {
  const warnings = asRecord(await put(b, "/api/storage", { models_dir: dir }))?.["warnings"];
  return { warnings: Array.isArray(warnings) ? warnings.filter((w): w is string => typeof w === "string") : [] };
}

export const startMove = async (b: Backend, target: string, source: string) =>
  parseMove(await post(b, "/api/storage/move", { target, source }));
export const fetchMove = async (b: Backend) => parseMove(await call(b, "/api/storage/move"));

/** Opens an https address in the default browser. The app, not the page, decides what may open. */
export function openUrl(url: string): Promise<void> {
  return invoke("open_url", { url });
}
