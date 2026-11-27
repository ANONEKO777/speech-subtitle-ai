/**
 * A text from the backend or the shell, and the notices inside it (`backend/core/notices.py`,
 * `src-tauri/src/notice.rs`). This is the wire half, read where a reply is parsed. `notice.ts` words
 * it where it is shown. It imports nothing, so the parsers can use it.
 */

export interface Notice {
  readonly code: string;
  readonly params: Readonly<Record<string, string | readonly string[]>>;
  /** The complete English sentence. */
  readonly message: string;
}

/**
 * Kept as it came, so that it is worded when it is shown and follows a change of language. A text
 * with no notices is shown as it is, which is how a text stored by an earlier version shows.
 */
export interface Said {
  readonly text: string;
  /** Outermost first: a notice's own parameter may quote a later one. */
  readonly notices: readonly Notice[];
}

export const plainText = (text: string): Said => ({ text, notices: [] });

const record = (value: unknown): Record<string, unknown> | null =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const isValue = (value: unknown): value is string | string[] =>
  typeof value === "string" || (Array.isArray(value) && value.every((item) => typeof item === "string"));

/** The notices of a reply, with anything that is not one left out. */
export function parseNotices(raw: unknown): Notice[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item): Notice[] => {
    const o = record(item);
    const params = record(o?.["params"]);
    if (typeof o?.["code"] !== "string" || typeof o["message"] !== "string" || o["message"] === "" || !params) return [];
    if (!Object.values(params).every(isValue)) return [];
    return [{ code: o["code"], message: o["message"], params: params as Notice["params"] }];
  });
}

/**
 * What a failed request or command said. It reads an `ApiError` (`message` and `notices`), the
 * shell's `{ message, notices }`, any other `Error`, and a plain string.
 */
export function said(error: unknown): Said {
  const o = record(error);
  if (typeof o?.["message"] === "string") return { text: o["message"], notices: parseNotices(o["notices"]) };
  return plainText(String(error));
}

/** A text field of a reply and the notices inside it, as in `error` and `error_notices`. */
export const saidField = (o: Readonly<Record<string, unknown>>, key: string): Said => ({
  text: typeof o[key] === "string" ? o[key] : "",
  notices: parseNotices(o[`${key}_notices`]),
});
