import { cueMark } from "../api/sourceLang";
import { useT } from "../i18n/I18nProvider";

/** The one letter that says which language a cue is in. It only shows in a mixed talk, where the cues differ. */
export function LangMark({ lang }: { readonly lang: string }) {
  const { t } = useT();
  const { mark, name } = cueMark(lang, t);
  return (
    <b className="lang-mark" data-testid="lang-mark" data-cue-lang={lang} title={name} aria-label={name}>
      {mark}
    </b>
  );
}
