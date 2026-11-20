import type { LanguageInfo } from "./client";
import type { SourceLang } from "./sourceLang";

/** A language a video in some source language can be translated into. */
export interface Target {
  readonly code: string;
  readonly name: string;
  readonly nativeName: string;
  /** The backend says this pair is not yet judged: a Japanese talk into Korean, for one. */
  readonly experimental: boolean;
}

/** `sources[].targets` of `GET /api/languages`, by source language, in the order the backend lists them. */
export type SourceTargets = Readonly<Partial<Record<string, readonly Target[]>>>;

const asObject = (v: unknown): Record<string, unknown> | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null;

export function parseSourceTargets(sources: unknown): SourceTargets {
  if (!Array.isArray(sources)) return {};
  const out: Record<string, readonly Target[]> = {};
  for (const item of sources as unknown[]) {
    const s = asObject(item);
    if (typeof s?.["code"] !== "string" || !Array.isArray(s["targets"])) continue;
    out[s["code"]] = (s["targets"] as unknown[]).flatMap((t): Target[] => {
      const o = asObject(t);
      if (typeof o?.["code"] !== "string" || typeof o["name"] !== "string" || typeof o["native_name"] !== "string") return [];
      return [{ code: o["code"], name: o["name"], nativeName: o["native_name"], experimental: o["experimental"] === true }];
    });
  }
  return out;
}

interface TargetSource {
  readonly languages: readonly LanguageInfo[];
  readonly targets: SourceTargets;
}

/**
 * The languages a video in `source` can be translated into. The backend's own list decides. A
 * backend that gives none for a source (an older one) offers every language but the source's own.
 */
export function targetsOf(set: TargetSource, source: SourceLang): readonly Target[] {
  const listed = set.targets[source];
  if (listed !== undefined) return listed;
  return set.languages
    .filter((l) => l.code !== source)
    .map((l) => ({ code: l.code, name: l.name, nativeName: l.nativeName, experimental: l.quality === "experimental" }));
}

/** `wanted` when `source` can be translated into it, else the first language it can. */
export function targetFor(set: TargetSource, source: SourceLang, wanted: string): string {
  const all = targetsOf(set, source);
  return all.some((t) => t.code === wanted) ? wanted : (all[0]?.code ?? wanted);
}

/** `wanted` without the languages `source` cannot use, in the order the backend lists them. At least one stays. */
export function targetsFor(set: TargetSource, source: SourceLang, wanted: readonly string[]): readonly string[] {
  const kept = targetsOf(set, source).filter((t) => wanted.includes(t.code)).map((t) => t.code);
  return kept.length > 0 ? kept : [targetFor(set, source, wanted[0] ?? "")];
}

export const EXPERIMENTAL = "實驗性";

/** What a person is told once they pick a language that is not yet judged. */
export const EXPERIMENTAL_HINT =
  "實驗性：這個語言的翻譯品質還沒有評分。有些句子可能翻不出來，會留空或改用英文顯示，請自己檢查。";

export const targetName = (set: TargetSource, source: SourceLang, code: string): string =>
  targetsOf(set, source).find((t) => t.code === code)?.nativeName ?? set.languages.find((l) => l.code === code)?.nativeName ?? code;

export const isExperimentalTarget = (set: TargetSource, source: SourceLang, code: string): boolean =>
  targetsOf(set, source).find((t) => t.code === code)?.experimental ?? false;
