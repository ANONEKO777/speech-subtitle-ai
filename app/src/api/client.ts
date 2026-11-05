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
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const base = (b: Backend) => `http://127.0.0.1:${b.port}`;

export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

async function call(b: Backend, path: string, init: RequestInit = {}): Promise<unknown> {
  const res = await fetch(base(b) + path, {
    ...init,
    headers: {
      authorization: `Bearer ${b.token}`,
      ...(init.body === undefined ? {} : { "content-type": "application/json" }),
    },
  });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = asRecord(body)?.["detail"];
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.statusText);
  }
  return body;
}

function projectView(body: unknown): ProjectView {
  const o = asRecord(body);
  const translate = asRecord(asRecord(o?.["steps"])?.["translate"]);
  if (typeof o?.["id"] !== "string" || typeof o["video_path"] !== "string") {
    throw new ApiError(500, "unexpected project reply");
  }
  const job = o["active_job"];
  return {
    id: o["id"],
    videoPath: o["video_path"],
    translated: translate?.["status"] === "done",
    activeJob: typeof job === "string" ? job : null,
  };
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

export async function fetchCues(b: Backend, projectId: string): Promise<Cue[]> {
  const body = asRecord(await call(b, `/api/projects/${projectId}/subtitles?lang=bilingual&format=json`));
  const list = body?.["cues"];
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

export function eventsUrl(b: Backend, jobId: string): string {
  return `${base(b)}/api/jobs/${jobId}/events?token=${encodeURIComponent(b.token)}`;
}
