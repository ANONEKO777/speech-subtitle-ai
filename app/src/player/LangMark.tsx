import { cueMark } from "../api/sourceLang";

/** The one letter that says which language a cue is in. It only shows in a mixed talk, where the cues differ. */
export function LangMark({ lang }: { readonly lang: string }) {
  const { mark, name } = cueMark(lang);
  return (
    <b className="lang-mark" data-testid="lang-mark" data-cue-lang={lang} title={name} aria-label={name}>
      {mark}
    </b>
  );
}
