import { type Translate, tZhTW } from "../i18n";
import type { LlmBody } from "../manage/api";
import type { LlmSaved, LlmSource } from "../manage/types";

export interface LlmDraft {
  readonly source: LlmSource;
  readonly ollamaUrl: string;
  readonly ollamaModel: string;
  readonly cloudUrl: string;
  readonly cloudModel: string;
  /** Ticked by the person each time a cloud source is saved. */
  readonly consent: boolean;
  /** Write only: never filled from the backend. */
  readonly apiKey: string;
}

export type LlmField = "ollamaUrl" | "ollamaModel" | "cloudUrl" | "cloudModel" | "apiKey" | "consent";

export interface LlmCheck {
  readonly errors: Readonly<Partial<Record<LlmField, string>>>;
  readonly canSave: boolean;
  readonly canTest: boolean;
}

export const DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434";

export const draftFrom = (saved: LlmSaved): LlmDraft => ({
  source: saved.source,
  ollamaUrl: saved.ollamaUrl || DEFAULT_OLLAMA_URL,
  ollamaModel: saved.ollamaModel,
  cloudUrl: saved.cloudUrl,
  cloudModel: saved.cloudModel,
  consent: saved.source === "cloud" && saved.cloudConsent,
  apiKey: "",
});

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const trimmed = (url: string) => url.trim().replace(/\/+$/, "");

/** An http(s) address with a host. Cloud addresses must be https unless they point at this machine. */
function urlError(raw: string, secure: boolean, t: Translate): string | null {
  const text = raw.trim();
  if (text === "") return t("llm.err.urlEmpty");
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return t("llm.err.urlInvalid");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return t("llm.err.urlScheme");
  if (secure && url.protocol !== "https:" && !LOOPBACK.has(url.hostname)) return t("llm.err.urlHttps");
  return null;
}

export function validateLlm(draft: LlmDraft, saved: LlmSaved, t: Translate = tZhTW): LlmCheck {
  const errors: Partial<Record<LlmField, string>> = {};
  let canTest = true;
  if (draft.source === "ollama") {
    const e = urlError(draft.ollamaUrl, false, t);
    if (e) errors.ollamaUrl = e;
    if (draft.ollamaModel.trim() === "") errors.ollamaModel = t("llm.err.ollamaModel");
    canTest = e === null;
  }
  if (draft.source === "cloud") {
    const e = urlError(draft.cloudUrl, true, t);
    if (e) errors.cloudUrl = e;
    if (draft.cloudModel.trim() === "") errors.cloudModel = t("llm.err.modelEmpty");
    const moved = trimmed(draft.cloudUrl) !== trimmed(saved.cloudUrl);
    if (draft.apiKey === "" && (!saved.apiKeySet || moved)) {
      errors.apiKey = saved.apiKeySet && moved ? t("llm.err.keyMoved") : t("llm.err.keyEmpty");
    }
    if (!draft.consent) errors.consent = t("llm.err.consent");
    canTest = e === null && errors.apiKey === undefined;
  }
  const { consent, ...rest } = errors;
  return { errors, canSave: Object.keys(rest).length === 0 && consent === undefined, canTest };
}

export function toBody(draft: LlmDraft): LlmBody {
  return {
    source: draft.source,
    ollama_url: draft.ollamaUrl.trim(),
    ollama_model: draft.ollamaModel.trim(),
    cloud_url: draft.cloudUrl.trim(),
    cloud_model: draft.cloudModel.trim(),
    cloud_consent: draft.source === "cloud" && draft.consent,
    ...(draft.apiKey === "" ? {} : { api_key: draft.apiKey }),
  };
}
