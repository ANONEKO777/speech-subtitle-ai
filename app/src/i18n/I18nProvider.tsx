import { type ReactNode, createContext, useCallback, useContext, useLayoutEffect, useMemo, useState } from "react";
import { type ArgsFor, type Key, type PluralBase, plural, t } from ".";
import { HTML_LANG, type Locale, UNMANAGED_LOCALE, type UiLanguage, readMirror, resolveLocale, writeMirror } from "./locale";

interface I18n {
  readonly locale: Locale;
  /** What the setting holds: a locale, or `auto`. */
  readonly uiLanguage: UiLanguage;
  /** Applies a language at once and mirrors it for the next first paint. Saving it is the caller's job. */
  readonly setUiLanguage: (next: UiLanguage) => void;
}

const Context = createContext<I18n | null>(null);

export function I18nProvider({ children, initial, browserLanguages }: { children: ReactNode; initial?: UiLanguage; browserLanguages?: readonly string[] }) {
  const [uiLanguage, setState] = useState<UiLanguage>(() => initial ?? readMirror());
  const languages = browserLanguages ?? navigator.languages;
  const locale = resolveLocale(uiLanguage, languages);
  useLayoutEffect(() => {
    document.documentElement.lang = HTML_LANG[locale];
  }, [locale]);
  const setUiLanguage = useCallback((next: UiLanguage) => {
    setState(next);
    writeMirror(next);
  }, []);
  const value = useMemo(() => ({ locale, uiLanguage, setUiLanguage }), [locale, uiLanguage, setUiLanguage]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** The language state, or null outside a provider (a bare render, which speaks Traditional Chinese). */
export const useI18n = (): I18n | null => useContext(Context);

export function useT() {
  const locale = useI18n()?.locale ?? UNMANAGED_LOCALE;
  return useMemo(
    () => ({
      locale,
      t: <K extends Key>(key: K, ...args: ArgsFor<K>) => t(locale, key, ...args),
      plural: <B extends PluralBase>(base: B, n: number, ...args: ArgsFor<`${B}.other` & Key, "n">) => plural(locale, base, n, ...args),
    }),
    [locale],
  );
}
