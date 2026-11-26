import { ArrowDownToLine, FileVideo, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { pickVideo } from "../api/backend";
import { SOURCE_LANGS, type SourceLang, type Unavailable, parseSourceLang } from "../api/sourceLang";
import type { Target } from "../api/targets";
import type { Translate } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import { languageName } from "../i18n/languageName";
import type { Locale } from "../i18n/locale";
import { isMacShell } from "../platform";

interface PickProps {
  readonly busy: boolean;
  readonly sourceLang: SourceLang;
  readonly unavailable: Unavailable;
  readonly onSourceLang: (code: SourceLang) => void;
}

interface TargetProps {
  readonly busy: boolean;
  /** What the video language can be translated into, in the backend's order. */
  readonly targets: readonly Target[];
  readonly target: string;
  readonly onTarget: (code: string) => void;
}

const targetText = (target: Target, t: Translate, locale: Locale) => {
  const name = languageName(locale, target);
  return target.experimental ? t("import.targetExperimental", { name }) : name;
};

/**
 * The language the subtitles are translated into. One the backend has not judged says so in its option.
 * A video language with one target only (a mixed talk) has nothing to pick, so it shows the name as text and gives the room back to the path box.
 */
export function TargetPick({ busy, targets, target, onTarget }: TargetProps) {
  const { t, locale } = useT();
  const chosen = targets.find((t) => t.code === target);
  const experimental = chosen?.experimental === true;
  if (targets.length < 2) {
    return (
      <span className="source-pick target-pick target-fixed" data-testid="target-lang" data-experimental={experimental} title={t("import.targetTitle")}>
        <span className="collapsible">{t("import.target")}</span>
        <span>{chosen ? targetText(chosen, t, locale) : target}</span>
      </span>
    );
  }
  return (
    <label className="source-pick target-pick" title={t("import.targetTitle")}>
      <span className="collapsible">{t("import.target")}</span>
      <select
        data-testid="target-lang"
        data-experimental={experimental}
        aria-label={t("import.targetAria")}
        value={target}
        disabled={busy}
        onChange={(e) => onTarget(e.target.value)}
      >
        {targets.map((option) => (
          <option key={option.code} value={option.code}>
            {targetText(option, t, locale)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The choices of a video language. One this machine cannot process is shown but cannot be picked, and its option says why. */
export function SourceOptions({ unavailable }: { readonly unavailable: Unavailable }) {
  const { t } = useT();
  return SOURCE_LANGS.map((l) => {
    const why = unavailable[l.code];
    return (
      <option key={l.code} value={l.code} disabled={why !== undefined} title={why}>
        {why === undefined ? t(l.label) : t("import.sourceWhy", { label: t(l.label), why })}
      </option>
    );
  });
}

export function SourcePick({ busy, sourceLang, unavailable, onSourceLang }: PickProps) {
  const { t } = useT();
  return (
    <label className="source-pick" title={t("import.sourceTitle")}>
      <span className="collapsible">{t("import.source")}</span>
      <select
        data-testid="source-lang"
        data-source={sourceLang}
        aria-label={t("import.source")}
        value={sourceLang}
        disabled={busy}
        onChange={(e) => onSourceLang(parseSourceLang(e.target.value))}
      >
        <SourceOptions unavailable={unavailable} />
      </select>
    </label>
  );
}

interface Props extends PickProps, TargetProps {
  readonly withPicker: boolean;
  readonly onImport: (videoPath: string) => void;
  /** The path in the box as it changes, and an empty one when it is imported: the box then keeps the path but it has been used. */
  readonly onPath: (videoPath: string) => void;
}

export function ImportPanel({ busy, sourceLang, unavailable, onSourceLang, targets, target, onTarget, withPicker, onImport, onPath }: Props) {
  const { t } = useT();
  const [path, setPath] = useState("");

  async function browse() {
    const picked = await pickVideo();
    if (picked) setPath(picked);
  }

  const trimmed = path.trim().replace(/^"(.*)"$/, "$1");
  useEffect(() => {
    onPath(trimmed);
  }, [trimmed, onPath]);
  return (
    <form
      className="import"
      onSubmit={(e) => {
        e.preventDefault();
        if (!trimmed) return;
        onPath("");
        onImport(trimmed);
      }}
    >
      <div className="field">
        <FileVideo className="icon" aria-hidden />
        <input
          data-testid="video-path"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder={isMacShell() ? t("import.pathPlaceholderMac") : t("import.pathPlaceholder")}
          spellCheck={false}
        />
      </div>
      {withPicker && <SourcePick busy={busy} sourceLang={sourceLang} unavailable={unavailable} onSourceLang={onSourceLang} />}
      {withPicker && <TargetPick busy={busy} targets={targets} target={target} onTarget={onTarget} />}
      <button type="button" title={t("import.pick")} onClick={() => void browse()} disabled={busy}>
        <FolderOpen className="icon" aria-hidden />
        <span className="collapsible">{t("import.pick")}</span>
      </button>
      <button type="submit" className="primary" data-testid="import" disabled={busy || !trimmed}>
        <ArrowDownToLine className="icon" aria-hidden />
        {t("import.go")}
      </button>
    </form>
  );
}
