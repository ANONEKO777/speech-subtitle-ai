import { ArrowDownToLine, FileVideo, FolderOpen } from "lucide-react";
import { useState } from "react";
import { pickVideo } from "../api/backend";
import { SOURCE_LANGS, type SourceLang, parseSourceLang } from "../api/sourceLang";

interface PickProps {
  readonly busy: boolean;
  readonly sourceLang: SourceLang;
  readonly onSourceLang: (code: SourceLang) => void;
}

export function SourcePick({ busy, sourceLang, onSourceLang }: PickProps) {
  return (
    <label className="source-pick" title="影片裡的人說的語言">
      <span className="collapsible">影片語言</span>
      <select
        data-testid="source-lang"
        aria-label="影片語言"
        value={sourceLang}
        disabled={busy}
        onChange={(e) => onSourceLang(parseSourceLang(e.target.value))}
      >
        {SOURCE_LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}

interface Props extends PickProps {
  readonly withPicker: boolean;
  readonly onImport: (videoPath: string) => void;
}

export function ImportPanel({ busy, sourceLang, onSourceLang, withPicker, onImport }: Props) {
  const [path, setPath] = useState("");

  async function browse() {
    const picked = await pickVideo();
    if (picked) setPath(picked);
  }

  const trimmed = path.trim().replace(/^"(.*)"$/, "$1");
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
      {withPicker && <SourcePick busy={busy} sourceLang={sourceLang} onSourceLang={onSourceLang} />}
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
