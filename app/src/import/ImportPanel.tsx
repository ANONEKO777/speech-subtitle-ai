import { ArrowDownToLine, FileVideo, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { pickVideo } from "../api/backend";
import { SOURCE_LANGS, type SourceLang, type Unavailable, parseSourceLang } from "../api/sourceLang";

interface PickProps {
  readonly busy: boolean;
  readonly sourceLang: SourceLang;
  readonly unavailable: Unavailable;
  readonly onSourceLang: (code: SourceLang) => void;
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

interface Props extends PickProps {
  readonly withPicker: boolean;
  readonly onImport: (videoPath: string) => void;
  /** The path in the box once it has stopped changing for a moment, or an empty one. */
  readonly onPath: (videoPath: string) => void;
}

const PATH_SETTLE_MS = 500;

export function ImportPanel({ busy, sourceLang, unavailable, onSourceLang, withPicker, onImport, onPath }: Props) {
  const [path, setPath] = useState("");

  async function browse() {
    const picked = await pickVideo();
    if (picked) setPath(picked);
  }

  const trimmed = path.trim().replace(/^"(.*)"$/, "$1");
  useEffect(() => {
    const timer = window.setTimeout(() => onPath(trimmed), trimmed === "" ? 0 : PATH_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [trimmed, onPath]);
  return (
    <form
      className="import"
      onSubmit={(e) => {
        e.preventDefault();
        if (trimmed) onImport(trimmed);
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
