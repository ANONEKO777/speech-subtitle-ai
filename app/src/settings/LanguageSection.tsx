import { Languages } from "lucide-react";
import { useState } from "react";
import type { Backend } from "../api/client";
import { useI18n, useT } from "../i18n/I18nProvider";
import { HTML_LANG, type Locale, MACHINE_TRANSLATED, RELEASED_LOCALES, type UiLanguage } from "../i18n/locale";
import { saveUiLanguage } from "../manage/api";
import { type Said, said, word } from "../i18n/notice";

/** A language written in itself, such as 日本語. The browser's own table, not ours. */
function ownName(locale: Locale): string {
  const tag = HTML_LANG[locale];
  try {
    return new Intl.DisplayNames([tag], { type: "language" }).of(tag) ?? tag;
  } catch {
    return tag;
  }
}

export function LanguageSection({ backend, released = RELEASED_LOCALES }: { backend: Backend; released?: readonly Locale[] }) {
  const { t } = useT();
  const i18n = useI18n();
  const [error, setError] = useState<Said | null>(null);
  const [saved, setSaved] = useState(false);
  if (!i18n) return null;
  const { uiLanguage, setUiLanguage } = i18n;
  const choices: readonly Locale[] = uiLanguage !== "auto" && !released.includes(uiLanguage) ? [...released, uiLanguage] : released;

  const pick = (next: UiLanguage) => {
    const before = uiLanguage;
    setUiLanguage(next);
    setError(null);
    setSaved(false);
    saveUiLanguage(backend, next).then(
      () => setSaved(true),
      (e: unknown) => {
        setUiLanguage(before);
        setError(said(e));
      },
    );
  };

  return (
    <section className="panel" data-testid="language-section" aria-labelledby="language-title">
      <div className="panel-head">
        <div>
          <h2 id="language-title">{t("language.title")}</h2>
          <p className="muted">{t("language.hint")}</p>
        </div>
      </div>
      <div className="card manage-card">
        <div className="fields">
          <div className="field-row">
            <label className="field-label" htmlFor="ui-language">
              {t("language.label")}
            </label>
            <select id="ui-language" className="text-input" data-testid="ui-language" value={uiLanguage} onChange={(e) => pick(e.target.value as UiLanguage)}>
              <option value="auto">{t("language.auto")}</option>
              {choices.map((locale) => (
                <option key={locale} value={locale} lang={HTML_LANG[locale]}>
                  {MACHINE_TRANSLATED.includes(locale) ? t("language.machine", { name: ownName(locale) }) : ownName(locale)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="sub">
          <Languages className="icon" aria-hidden /> {t("language.note")}
        </p>
        {saved && (
          <p className="note ok" role="status" data-testid="language-saved">
            {t("language.saved")}
          </p>
        )}
        {error && (
          <p className="note bad" role="alert" data-testid="language-error">
            {t("language.failed", { reason: word(error, i18n.locale) })}
          </p>
        )}
      </div>
    </section>
  );
}
