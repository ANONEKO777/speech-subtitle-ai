import { ApiError, type Backend, asRecord, base, call } from "./client";
import { type SourceLang, parseSourceLang } from "./sourceLang";
import { type Said, saidField } from "../i18n/said";

export interface LibraryItem {
  readonly id: string;
  readonly videoPath: string;
  readonly title: string;
  readonly exists: boolean;
  readonly langs: readonly string[];
  readonly sourceLang: SourceLang;
  readonly durationS: number;
  readonly positionS: number;
  readonly openedAtMs: number;
}

export interface Playback {
  readonly positionS: number;
  readonly durationS: number;
  readonly offsetMs: number;
}

export const NO_PLAYBACK: Playback = { positionS: 0, durationS: 0, offsetMs: 0 };

const num = (v: unknown, fallback = 0) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

export async function fetchLibrary(b: Backend): Promise<LibraryItem[]> {
  const list = asRecord(await call(b, "/api/projects"))?.["projects"];
  if (!Array.isArray(list)) throw new ApiError(500, "unexpected library reply");
  return list.flatMap((item): LibraryItem[] => {
    const o = asRecord(item);
    if (typeof o?.["id"] !== "string" || typeof o["video_path"] !== "string") return [];
    const langs = Array.isArray(o["langs"]) ? o["langs"].filter((l): l is string => typeof l === "string") : [];
    return [
      {
        id: o["id"],
        videoPath: o["video_path"],
        title: typeof o["title"] === "string" ? o["title"] : o["id"],
        exists: o["exists"] === true,
        langs,
        sourceLang: parseSourceLang(o["source_lang"]),
        durationS: num(o["duration_s"]),
        positionS: num(o["position_s"]),
        openedAtMs: num(o["opened_at_ms"]),
      },
    ];
  });
}

const playback = (body: unknown): Playback => {
  const o = asRecord(body);
  return { positionS: num(o?.["position_s"]), durationS: num(o?.["duration_s"]), offsetMs: num(o?.["offset_ms"]) };
};

export async function fetchPlayback(b: Backend, projectId: string): Promise<Playback> {
  return playback(await call(b, `/api/projects/${projectId}/playback`));
}

/** Frames per second of the picture, or null when ffprobe cannot tell. */
export async function fetchFrameRate(b: Backend, projectId: string): Promise<number | null> {
  const rate = asRecord(await call(b, `/api/projects/${projectId}/media`))?.["frame_rate"];
  return typeof rate === "number" && rate > 0 ? rate : null;
}

export interface PlaybackChange {
  readonly positionS?: number;
  readonly durationS?: number;
  readonly offsetMs?: number;
  readonly opened?: boolean;
}

export async function putPlayback(b: Backend, projectId: string, c: PlaybackChange, keepalive = false): Promise<Playback> {
  const body = JSON.stringify({
    position_s: c.positionS,
    duration_s: c.durationS,
    offset_ms: c.offsetMs,
    opened: c.opened ?? false,
  });
  const res = await fetch(`${base(b)}/api/projects/${projectId}/playback`, {
    method: "PUT",
    headers: { authorization: `Bearer ${b.token}`, "content-type": "application/json" },
    body,
    keepalive,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return playback(await res.json());
}

/** The thumbnail as an object URL the caller must revoke, or null when it cannot be made. */
export async function fetchThumbnail(b: Backend, projectId: string): Promise<string | null> {
  const res = await fetch(`${base(b)}/api/projects/${projectId}/thumbnail`, {
    headers: { authorization: `Bearer ${b.token}` },
  });
  return res.ok ? URL.createObjectURL(await res.blob()) : null;
}

/** How burned subtitles look, from the person's subtitle settings. */
export interface Look {
  readonly mode: "en" | "zh" | "both";
  readonly zhFirst: boolean;
  /** The font height over the picture height. */
  readonly sizeRatio: number;
  readonly color: string;
}

const lookBody = (l: Look) => ({ mode: l.mode, zh_first: l.zhFirst, size_ratio: l.sizeRatio, color: l.color });

export interface Still {
  readonly path: string;
  readonly png: Blob;
}

export async function takeStill(
  b: Backend,
  projectId: string,
  req: { timeS: number; lang: string; burn: boolean; dir: string; look: Look },
): Promise<Still> {
  const body = JSON.stringify({
    ...lookBody(req.look),
    time_s: req.timeS,
    lang: req.lang,
    burn: req.burn,
    dir: req.dir || null,
  });
  const o = asRecord(await call(b, `/api/projects/${projectId}/screenshot`, { method: "POST", body }));
  if (typeof o?.["path"] !== "string" || typeof o["png_base64"] !== "string") throw new ApiError(500, "unexpected screenshot reply");
  const bytes = Uint8Array.from(atob(o["png_base64"]), (c) => c.charCodeAt(0));
  return { path: o["path"], png: new Blob([bytes], { type: "image/png" }) };
}

export type BurnState = "running" | "done" | "failed" | "cancelled";

export interface BurnView {
  readonly id: string;
  readonly state: BurnState;
  readonly percent: number;
  readonly output: string;
  readonly error: Said | null;
}

export const burnViewOf = (body: unknown): BurnView => {
  const o = asRecord(body);
  const state = o?.["state"];
  if (typeof o?.["id"] !== "string" || (state !== "running" && state !== "done" && state !== "failed" && state !== "cancelled")) {
    throw new ApiError(500, "unexpected export reply");
  }
  return {
    id: o["id"],
    state,
    percent: num(o["percent"]),
    output: typeof o["output"] === "string" ? o["output"] : "",
    error: typeof o["error"] === "string" ? saidField(o, "error") : null,
  };
};

export async function startBurn(
  b: Backend,
  projectId: string,
  req: { lang: string; dir: string; look: Look; startS: number; durationS: number | null },
): Promise<BurnView> {
  const body = JSON.stringify({
    ...lookBody(req.look),
    lang: req.lang,
    dir: req.dir || null,
    start_s: req.startS,
    duration_s: req.durationS,
  });
  return burnViewOf(await call(b, `/api/projects/${projectId}/burn`, { method: "POST", body }));
}

export async function fetchBurn(b: Backend, id: string): Promise<BurnView> {
  return burnViewOf(await call(b, `/api/burns/${id}`));
}

export async function cancelBurn(b: Backend, id: string): Promise<void> {
  await call(b, `/api/burns/${id}/cancel`, { method: "POST" });
}
