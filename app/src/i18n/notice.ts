/**
 * Words the sentences the backend and the shell send (`backend/core/notices.py`,
 * `src-tauri/src/notice.rs`). They send an English text and the notices inside it, each
 * `{ code, params, message }`. The window replaces each notice's English `message` inside the text
 * with the catalog's `notice.<code>`, and leaves a code it cannot word as it came.
 */
import { type Key, t } from "./index";
import { CATALOGS } from "./catalog";
import { languageName } from "./languageName";
import type { Locale } from "./locale";
import type { Notice, Said } from "./said";
import backend from "./notices.backend.json";
import shell from "./notices.shell.json";

export type { Notice, Said } from "./said";
export { parseNotices, plainText, said, saidField } from "./said";

type ParamKind = "text" | "list" | "language";

/** Every code a sender has, with the kind of each parameter. */
export const SENT: Readonly<Record<string, { readonly english: string; readonly params: Readonly<Record<string, string>> }>> = {
  ...backend,
  ...shell,
};

function shownParam(kind: ParamKind, value: string | readonly string[], locale: Locale): string | null {
  if (kind === "list") return Array.isArray(value) ? value.join(t(locale, "common.listSeparator")) : null;
  if (typeof value !== "string") return null;
  return kind === "language" ? languageName(locale, { code: value }) : value;
}

/** The catalog's sentence for `notice`, or its English `message` when the code or a parameter is unknown. */
export function wordNotice(notice: Notice, locale: Locale): string {
  const key = `notice.${notice.code}`;
  const sent = Object.hasOwn(SENT, notice.code) ? SENT[notice.code] : undefined;
  if (sent === undefined || !Object.hasOwn(CATALOGS[locale], key)) return notice.message;
  let known = true;
  const worded = CATALOGS[locale][key as Key].replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = notice.params[name];
    const shown = value === undefined ? null : shownParam(sent.params[name] as ParamKind, value, locale);
    if (shown === null) known = false;
    return shown ?? "";
  });
  return known ? worded : notice.message;
}

/** The text in the language of the window. */
export const word = (said: Said, locale: Locale): string =>
  said.notices.reduce((text, notice) => {
    const shown = wordNotice(notice, locale);
    return text.replaceAll(notice.message, () => shown);
  }, said.text);
