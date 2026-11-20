import { ArrowDownToLine, FileVideo, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { pickVideo } from "../api/backend";
import { SOURCE_LANGS, type SourceLang, type Unavailable, parseSourceLang } from "../api/sourceLang";
import { EXPERIMENTAL, type Target } from "../api/targets";
import { shortName } from "../export/exports";

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

/** The language the subtitles are translated into. One the backend has not judged says so in its option. */
export function TargetPick({ busy, targets, target, onTarget }: TargetProps) {
  const experimental = targets.find((t) => t.code === target)?.experimental === true;
  return (
    <label className="source-pick target-pick" title="字幕要翻成的語言">
      <span className="collapsible">字幕語言</span>
      <select
        data-testid="target-lang"
        data-experimental={experimental}
        aria-label="字幕語言"
        value={target}
        disabled={busy || targets.length < 2}
        onChange={(e) => onTarget(e.target.value)}
      >
        {targets.map((t) => (
          <option key={t.code} value={t.code}>
            {shortName(t.nativeName)}
            {t.experimental ? `（${EXPERIMENTAL}）` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The choices of a video language. One this machine cannot process is shown but cannot be picked, and its option says why. */
export function SourceOptions({ unavailable }: { readonly unavailable: Unavailable }) {
  return SOURCE_LANGS.map((l) => {
    const why = unavailable[l.code];
    return (
      <option key={l.code} value={l.code} disabled={why !== undefined} title={why}>
        {why === undefined ? l.label : `${l.label}（${why}）`}
      </option>
    );
  });
}

export function SourcePick({ busy, sourceLang, unavailable, onSourceLang }: PickProps) {
  return (
    <label className="source-pick" title="影片裡的人說的語言">
      <span className="collapsible">影片語言</span>
      <select
        data-testid="source-lang"
        data-source={sourceLang}
        aria-label="影片語言"
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
          placeholder="影片的完整路徑，例如 D:\talks\talk.mp4"
          spellCheck={false}
        />
      </div>
      {withPicker && <SourcePick busy={busy} sourceLang={sourceLang} unavailable={unavailable} onSourceLang={onSourceLang} />}
      {withPicker && <TargetPick busy={busy} targets={targets} target={target} onTarget={onTarget} />}
      <button type="button" title="選擇檔案" onClick={() => void browse()} disabled={busy}>
        <FolderOpen className="icon" aria-hidden />
        <span className="collapsible">選擇檔案</span>
      </button>
      <button type="submit" className="primary" data-testid="import" disabled={busy || !trimmed}>
        <ArrowDownToLine className="icon" aria-hidden />
        匯入
      </button>
    </form>
  );
}
