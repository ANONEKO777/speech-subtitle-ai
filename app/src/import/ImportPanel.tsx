import { ArrowDownToLine, FileVideo, FolderOpen } from "lucide-react";
import { useState } from "react";
import { pickVideo } from "../api/backend";

interface Props {
  readonly busy: boolean;
  readonly onImport: (videoPath: string) => void;
}

export function ImportPanel({ busy, onImport }: Props) {
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
