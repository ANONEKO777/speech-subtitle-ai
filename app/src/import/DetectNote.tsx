import { LoaderCircle } from "lucide-react";
import { type Detected, detectLine, hintFor, isDetection, switchLabel } from "../api/detect";
import type { SourceLang, Unavailable } from "../api/sourceLang";

interface Props {
  readonly found: Detected | undefined;
  readonly picked: SourceLang;
  readonly unavailable: Unavailable;
  readonly onSwitch: (code: SourceLang) => void;
}

/** Whether the note has anything to say, so the bar that holds it can stay away when it has not. */
export const hasDetectNote = (found: Detected | undefined): boolean =>
  found === "running" || (isDetection(found) && detectLine(found) !== null);

/** What was heard in the picked video, and a one-click switch when the picked language differs from a clear guess. */
export function DetectNote({ found, picked, unavailable, onSwitch }: Props) {
  if (found === "running") {
    return (
      <p className="detect-note" data-testid="detect-note" data-state="running">
        <LoaderCircle className="spin icon" aria-hidden />
        正在偵測影片語言…
      </p>
    );
  }
  if (!isDetection(found)) return null;
  const line = detectLine(found);
  if (line === null) return null;
  const hint = hintFor(found, picked, unavailable);
  return (
    <>
      <p className="detect-note" data-testid="detect-note" data-state="done" data-detected={found.detected ?? ""}>
        {line}
      </p>
      {hint && (
        <p className="detect-hint" data-testid="detect-hint" role="status">
          {hint.text}
          <button type="button" data-testid="detect-switch" onClick={() => onSwitch(hint.switchTo)}>
            {switchLabel(hint.switchTo)}
          </button>
        </p>
      )}
    </>
  );
}
