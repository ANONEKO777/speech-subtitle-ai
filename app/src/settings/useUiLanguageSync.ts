import { useEffect } from "react";
import type { Backend } from "../api/client";
import { useI18n } from "../i18n/I18nProvider";
import { fetchSettings } from "../manage/api";

/** Once the backend answers, the saved window language replaces the mirror the first paint used. */
export function useUiLanguageSync(backend: Backend | null): void {
  const setUiLanguage = useI18n()?.setUiLanguage;
  useEffect(() => {
    if (!backend || !setUiLanguage) return;
    let alive = true;
    fetchSettings(backend).then(
      (view) => alive && setUiLanguage(view.uiLanguage),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [backend, setUiLanguage]);
}
