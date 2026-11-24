/** What the manager routes return, parsed once at the boundary (see `parse.ts`). */

export type ProfileId = "gpu-24gb" | "gpu-8gb" | "cpu" | "metal-32gb" | "metal-32gb-parallel" | "metal-16gb" | "apple-cpu";
export const PROFILE_IDS: readonly ProfileId[] = ["gpu-24gb", "gpu-8gb", "cpu", "metal-32gb", "metal-32gb-parallel", "metal-16gb", "apple-cpu"];

export type InstallState = "not_installed" | "partial" | "installing" | "installed";
export type ShaState = "verified" | "unchecked" | "corrupt" | "not_installed";

export interface Dependent {
  readonly id: string;
  readonly installed: boolean;
}

export interface Asset {
  readonly id: string;
  readonly type: "model" | "runtime";
  readonly kind: string;
  readonly state: InstallState;
  /** What the registry ships. */
  readonly version: string;
  readonly installedVersion: string | null;
  readonly sizeBytes: number;
  readonly sizeOnDisk: number | null;
  readonly path: string | null;
  readonly shaState: ShaState;
  /** A runtime is an unpacked zip: only the archive was hashed, at install time. */
  readonly shaScope: "file" | "archive_at_install";
  readonly usedByProfiles: readonly string[];
  readonly inActiveProfile: boolean;
  readonly dependents: readonly Dependent[];
  /** Why a plain delete is refused. */
  readonly blockers: readonly string[];
  readonly license: string;
  readonly licenseUrl: string;
  /** Built on this machine by a script, so there is nothing to download (`sizeBytes` is 0). */
  readonly localBuild: boolean;
}

export interface Inventory {
  readonly activeProfile: string;
  readonly modelsDir: string;
  readonly runtimesDir: string;
  readonly installedBytes: number;
  readonly assets: readonly Asset[];
}

export type JobState = "queued" | "downloading" | "verifying" | "extracting" | "done" | "failed" | "cancelled";

export interface JobFailure {
  readonly kind: string;
  readonly message: string;
}

export interface DownloadJob {
  readonly id: string;
  readonly assetId: string;
  readonly state: JobState;
  readonly bytesDone: number;
  readonly bytesTotal: number;
  readonly speedBps: number;
  readonly resumedFrom: number;
  readonly retries: number;
  readonly note: string | null;
  readonly failure: JobFailure | null;
}

export interface Hardware {
  /** `macos-arm64` for an Apple-silicon Mac, `win-x64` for a Windows PC. */
  readonly platform: string;
  /** The Apple chip's name ("Apple M3 Pro"); null on a PC. */
  readonly chip: string | null;
  readonly gpuName: string | null;
  readonly vramMib: number | null;
  readonly driverVersion: string | null;
  readonly ramMib: number | null;
  readonly diskFreeMib: number | null;
}

export interface MissingAsset {
  readonly id: string;
  readonly type: string;
  readonly sizeBytes: number;
  /** Built on this machine by a script, so there is nothing to download (`sizeBytes` is 0). */
  readonly localBuild: boolean;
}

export interface ProfileOption {
  readonly id: ProfileId;
  readonly label: string;
  readonly recommendCloud: boolean;
  readonly fitsHardware: boolean;
  readonly active: boolean;
  readonly recommended: boolean;
  readonly missing: readonly MissingAsset[];
  readonly downloadBytes: number;
  readonly asrModel: string;
  readonly llmModel: string;
}

export interface Fallback {
  readonly reason: string;
}

export interface ProfileView {
  readonly hardware: Hardware;
  /** The Microsoft Visual C++ runtime the downloaded programs import is not installed. */
  readonly vcRuntimeMissing: boolean;
  readonly recommended: { readonly id: ProfileId; readonly label: string; readonly why: string };
  readonly active: { readonly id: ProfileId; readonly label: string; readonly source: "user" | "recommended"; readonly device: string };
  readonly profiles: readonly ProfileOption[];
  readonly fallback: Fallback | null;
}

export interface ProfileSwitch {
  readonly view: ProfileView;
  readonly warnings: readonly string[];
}

export interface StageResult {
  readonly stage: string;
  readonly runtimeId: string;
  readonly device: string;
  readonly installed: boolean;
  readonly ok: boolean;
  readonly seconds: number;
  readonly detail: string;
}

export interface SelfTest {
  readonly ok: boolean;
  readonly device: string;
  readonly stages: readonly StageResult[];
  readonly fallback: Fallback | null;
  readonly seconds: number;
  readonly message: string;
}

export type LlmSource = "builtin" | "ollama" | "cloud";

export interface LlmSaved {
  readonly source: LlmSource;
  readonly ollamaUrl: string;
  readonly ollamaModel: string;
  readonly cloudUrl: string;
  readonly cloudModel: string;
  readonly cloudConsent: boolean;
  readonly apiKeySet: boolean;
}

export interface StorageView {
  readonly userData: string;
  readonly modelsDir: string;
  readonly customModelsDir: string | null;
}

export interface SettingsView {
  readonly llm: LlmSaved;
  readonly consentText: string;
  readonly problem: string | null;
  readonly storage: StorageView;
}

export interface LlmTest {
  readonly ok: boolean;
  readonly url: string;
  readonly detail: string;
  readonly models: readonly string[];
}

export interface UpdateItem {
  readonly id: string;
  readonly status: "not_installed" | "current" | "update_available" | "unknown";
  readonly installable: boolean;
  readonly message: string;
}

export interface UpdateReport {
  readonly message: string;
  readonly items: readonly UpdateItem[];
}

export interface LicenseEntry {
  readonly id: string;
  readonly type: string;
  readonly version: string;
  readonly license: string;
  readonly licenseUrl: string;
  readonly parts: readonly { readonly id: string; readonly url: string }[];
  readonly sourceUrl: string;
}

export type MoveState = "idle" | "running" | "done" | "failed";

export interface MoveStatus {
  readonly state: MoveState;
  readonly target: string | null;
  readonly filesTotal: number;
  readonly filesDone: number;
  readonly bytesTotal: number;
  readonly bytesDone: number;
  readonly error: string | null;
  readonly warnings: readonly string[];
}
