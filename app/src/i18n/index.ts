import { CATALOGS, type English, type Key } from "./catalog";
import { type Locale, UNMANAGED_LOCALE } from "./locale";

export type { Key } from "./catalog";

/** The `{name}` placeholders of a template, as a union of names. */
type Names<S extends string> = S extends `${string}{${infer N}}${infer Rest}` ? N | Names<Rest> : never;

export type Params = Readonly<Record<string, string | number>>;
/** The params a key needs, read off its English text. No placeholder means no argument. */
export type ArgsFor<K extends Key, Given extends string = never> = [Exclude<Names<English[K]>, Given>] extends [never]
  ? []
  : [params: Readonly<Record<Exclude<Names<English[K]>, Given>, string | number>>];

/** The keys whose text has no placeholder, so `t(key)` needs no params. */
export type PlainKey = { [K in Key]: [Names<English[K]>] extends [never] ? K : never }[Key];

/** The key before `.one` or `.other`, for the strings that change with a count. */
export type PluralBase = Key extends infer K ? (K extends `${infer B}.other` ? B : never) : never;

type OneBase = Key extends infer K ? (K extends `${infer B}.one` ? B : never) : never;
type PluralPairs = [Exclude<PluralBase, OneBase>, Exclude<OneBase, PluralBase>] extends [never, never] ? true : never;
/**
 * Compile-time proof that every plural key has both forms: a `.other` without its `.one`, or a
 * `.one` without its `.other`, makes this line fail `tsc`. (`plural` reads both forms by name.)
 */
export const everyPluralHasBothForms: PluralPairs = true;

/** What a component gets from `useT().t`, and what a helper that returns text takes in. */
export type Translate = <K extends Key>(key: K, ...args: ArgsFor<K>) => string;
export type PluralTranslate = <B extends PluralBase>(base: B, n: number, ...args: ArgsFor<`${B}.other` & Key, "n">) => string;

function fill(template: string, params: Params | undefined): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params?.[name];
    return value === undefined ? whole : String(value);
  });
}

/** The text for `key` in `locale`. A placeholder with no value stays visible as `{name}`. */
export function t<K extends Key>(locale: Locale, key: K, ...args: ArgsFor<K>): string {
  return fill(CATALOGS[locale][key], args[0] as Params | undefined);
}

/**
 * The text of `base.one` or `base.other` that fits `n` in `locale`, with `{n}` filled in. Every
 * locale defines both forms, so a language without plurals repeats its one text.
 */
export function plural<B extends PluralBase>(locale: Locale, base: B, n: number, ...args: ArgsFor<`${B}.other` & Key, "n">): string {
  const category = new Intl.PluralRules(locale).select(n);
  const catalog = CATALOGS[locale] as Readonly<Record<string, string>>;
  const template = catalog[`${base}.${category}`] ?? catalog[`${base}.other`] ?? "";
  return fill(template, { n, ...(args[0] as Params | undefined) });
}

/**
 * The translator of a window with no provider, which speaks Traditional Chinese. A helper that
 * returns text takes a `Translate` last and defaults to this, so a caller that has not moved to
 * the catalog yet keeps its Chinese until its wave passes `useT().t`.
 */
export const tZhTW: Translate = (key, ...args) => t(UNMANAGED_LOCALE, key, ...args);
export const pluralZhTW: PluralTranslate = (base, n, ...args) => plural(UNMANAGED_LOCALE, base, n, ...args);
