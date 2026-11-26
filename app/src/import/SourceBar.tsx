import type { Detected } from "../api/detect";
import { type SourceLang, type Unavailable, sourceNote } from "../api/sourceLang";
import { useT } from "../i18n/I18nProvider";
import { DetectNote, hasDetectNote } from "./DetectNote";
import { SourcePick } from "./ImportPanel";

interface Props {
  /** In the player the video language picker moves into this bar, because the toolbar has no spare width there. */
  readonly playing: boolean;
  readonly busy: boolean;
  readonly sourceLang: SourceLang;
  readonly unavailable: Unavailable;
  readonly onSourceLang: (code: SourceLang) => void;
  readonly found: Detected | undefined;
  /** The subtitle language picked on the home screen has not been judged by the backend. */
  readonly experimentalPick: boolean;
}

/** The line under the toolbar: what to know about the video language and the subtitle language picked. It is not there when it has nothing to say. */
export function SourceBar({ playing, busy, sourceLang, unavailable, onSourceLang, found, experimentalPick }: Props) {
  const { t } = useT();
  const note = sourceNote(sourceLang, t);
  if (!note && !hasDetectNote(found) && !experimentalPick) return null;
  return (
    <div className="source-bar">
      {playing && <SourcePick busy={busy} sourceLang={sourceLang} unavailable={unavailable} onSourceLang={onSourceLang} />}
      {note && (
        <p className="source-note" data-testid="source-note">
          {note}
        </p>
      )}
      {experimentalPick && (
        <p className="source-note" data-testid="target-hint">
          {t("targets.experimentalHint")}
        </p>
      )}
      <DetectNote found={found} picked={sourceLang} unavailable={unavailable} onSwitch={onSourceLang} />
    </div>
  );
}
