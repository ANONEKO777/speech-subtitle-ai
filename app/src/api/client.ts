import type { Cue } from "../player/cues";

export interface Backend {
  readonly port: number;
  readonly token: string;
}

export interface ProjectView {
  readonly id: string;
  readonly videoPath: string;
  readonly translated: boolean;
  readonly activeJob: string | null;
  readonly activeLang: string;
  /** Codes of the languages whose translation is finished, the active one first. */
  readonly translatedLangs: readonly string[];
}

/** A cue the backend refused to save, with the reason. */
export interface CueProblem {
  readonly id: number;
  readonly code: string;
  readonly message: string;
  readonly other: number | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly problems: readonly CueProblem[] = [],
    /** The `detail` of the error body, for callers that read more than the message. */
    readonly detail: unknown = null,
  ) {
    super(message);
  }
}

export const base = (b: Backend) => `http://127.0.0.1:${b.port}`;

export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export async function call(b: Backend, path: string, init: RequestInit = {}): Promise<unknown> {
  const res = await fetch(base(b) + path, {
    ...init,
    headers: {
      authorization: `Bearer ${b.token}`,
      ...(init.body === undefined ? {} : { "content-type": "application/json" }),
    },
  });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw apiError(res.status, res.statusText, body);
  return body;
}

function apiError(status: number, statusText: string, body: unknown): ApiError {
  const detail = asRecord(body)?.["detail"];
  if (typeof detail === "string") return new ApiError(status, detail, [], detail);
  const o = asRecord(detail);
  const list = Array.isArray(o?.["problems"]) ? (o["problems"] as unknown[]) : [];
  const problems = list.flatMap((item): CueProblem[] => {
    const p = asRecord(item);
    if (typeof p?.["id"] !== "number" || typeof p["code"] !== "string") return [];
    const other = p["other"];
    return [{ id: p["id"], code: p["code"], message: String(p["message"] ?? ""), other: typeof other === "number" ? other : null }];
  });
  return new ApiError(status, typeof o?.["message"] === "string" ? o["message"] : statusText, problems, detail);
}

async function callText(b: Backend, path: string): Promise<string> {
  const res = await fetch(base(b) + path, { headers: { authorization: `Bearer ${b.token}` } });
  if (!res.ok) throw apiError(res.status, res.statusText, await res.json().catch(() => null));
  return res.text();
}

function projectView(body: unknown): ProjectView {
  const o = asRecord(body);
  const translate = asRecord(asRecord(o?.["steps"])?.["translate"]);
  if (typeof o?.["id"] !== "string" || typeof o["video_path"] !== "string") {
    throw new ApiError(500, "unexpected project reply");
  }
  const job = o["active_job"];
  const active = typeof o["active_lang"] === "string" ? o["active_lang"] : "zh-TW";
  const languages = asRecord(o["languages"]) ?? {};
  const translatedLangs = Object.entries(languages)
    .filter(([, steps]) => asRecord(asRecord(steps)?.["translate"])?.["status"] === "done")
    .map(([code]) => code)
    .sort((a, b) => Number(b === active) - Number(a === active));
  return {
    id: o["id"],
    videoPath: o["video_path"],
    translated: translate?.["status"] === "done",
    activeJob: typeof job === "string" ? job : null,
    activeLang: active,
    translatedLangs,
  };
}

export async function fetchProject(b: Backend, projectId: string): Promise<ProjectView> {
  return projectView(await call(b, `/api/projects/${projectId}`));
}

export interface LanguageInfo {
  readonly code: string;
  readonly name: string;
  readonly nativeName: string;
  /** Translation quality the backend vouches for; `experimental` is shown with a label. */
  readonly quality: "stable" | "experimental";
}

export interface LanguageSet {
  readonly defaultCode: string;
  readonly languages: LanguageInfo[];
}

export async function fetchLanguageSet(b: Backend): Promise<LanguageSet> {
  const body = asRecord(await call(b, "/api/languages"));
  const list = body?.["languages"];
  if (!Array.isArray(list)) throw new ApiError(500, "unexpected languages reply");
  const languages = list.flatMap((item): LanguageInfo[] => {
    const l = asRecord(item);
    if (typeof l?.["code"] !== "string" || typeof l["name"] !== "string" || typeof l["native_name"] !== "string") return [];
    const quality = l["quality"] === "experimental" ? "experimental" : "stable";
    return [{ code: l["code"], name: l["name"], nativeName: l["native_name"], quality }];
  });
  return { defaultCode: typeof body?.["default"] === "string" ? body["default"] : "zh-TW", languages };
}

export async function fetchLanguages(b: Backend): Promise<LanguageInfo[]> {
  return (await fetchLanguageSet(b)).languages;
}

export async function createProject(b: Backend, videoPath: string): Promise<ProjectView> {
  const body = JSON.stringify({ video_path: videoPath });
  return projectView(await call(b, "/api/projects", { method: "POST", body }));
}

export async function startJob(b: Backend, projectId: string): Promise<string> {
  const body = asRecord(await call(b, `/api/projects/${projectId}/jobs`, { method: "POST", body: "{}" }));
  if (typeof body?.["id"] !== "string") throw new ApiError(500, "unexpected job reply");
  return body["id"];
}

export async function cancelJob(b: Backend, jobId: string): Promise<void> {
  await call(b, `/api/jobs/${jobId}/cancel`, { method: "POST" });
}

const targetQuery = (lang: string) => `target_lang=${encodeURIComponent(lang)}`;

function parseCues(body: unknown): Cue[] {
  const list = asRecord(body)?.["cues"];
  if (!Array.isArray(list)) throw new ApiError(500, "unexpected subtitles reply");
  return list.map((item): Cue => {
    const c = asRecord(item);
    if (
      typeof c?.["id"] !== "number" ||
      typeof c["start_ms"] !== "number" ||
      typeof c["end_ms"] !== "number" ||
      typeof c["en"] !== "string" ||
      typeof c["zh"] !== "string"
    ) {
      throw new ApiError(500, "unexpected cue");
    }
    return { id: c["id"], startMs: c["start_ms"], endMs: c["end_ms"], en: c["en"], zh: c["zh"] };
  });
}

export async function fetchCues(b: Backend, projectId: string, lang: string): Promise<Cue[]> {
  return parseCues(await call(b, `/api/projects/${projectId}/subtitles?lang=bilingual&format=json&${targetQuery(lang)}`));
}

/** Saves the whole cue list of `lang`. The backend refuses it with `problems` naming the bad cues. */
export async function putCues(b: Backend, projectId: string, lang: string, cues: readonly Cue[]): Promise<void> {
  const body = JSON.stringify({
    cues: cues.map((c) => ({ id: c.id, start_ms: c.startMs, end_ms: c.endMs, en: c.en, zh: c.zh })),
  });
  await call(b, `/api/projects/${projectId}/subtitles?${targetQuery(lang)}`, { method: "PUT", body });
}

/** Ids of the cues a person corrected, which a rerun of translate keeps. */
export async function fetchEditedIds(b: Backend, projectId: string, lang: string): Promise<number[]> {
  const ids = asRecord(await call(b, `/api/projects/${projectId}/edits?${targetQuery(lang)}`))?.["ids"];
  return Array.isArray(ids) ? ids.filter((id): id is number => typeof id === "number") : [];
}

/** The summary of `lang`, or null while that language has none. */
export async function fetchSummary(b: Backend, projectId: string, lang: string): Promise<string | null> {
  try {
    return await callText(b, `/api/projects/${projectId}/summary?lang=${encodeURIComponent(lang)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) return null;
    throw e;
  }
}

/** Whether the summary of `lang` was written from a fallback (a degraded summarize step), which the reader should not trust as normal. */
export async function fetchSummaryDegraded(b: Backend, projectId: string, lang: string): Promise<boolean> {
  const steps = asRecord(asRecord(asRecord(await call(b, `/api/projects/${projectId}`))?.["languages"])?.[lang]);
  return asRecord(steps?.["summarize"])?.["degraded"] === true;
}

export interface SubtitleRequest {
  readonly show: "en" | "zh" | "bilingual";
  readonly format: "srt" | "vtt" | "ass";
}

export function fetchSubtitleText(b: Backend, projectId: string, lang: string, r: SubtitleRequest): Promise<string> {
  return callText(b, `/api/projects/${projectId}/subtitles?lang=${r.show}&format=${r.format}&${targetQuery(lang)}`);
}

export function eventsUrl(b: Backend, jobId: string): string {
  return `${base(b)}/api/jobs/${jobId}/events?token=${encodeURIComponent(b.token)}`;
}
