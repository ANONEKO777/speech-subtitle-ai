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
      <input
        data-testid="video-path"
        value={path}
        onChange={(e) => setPath(e.target.value)}
        placeholder="影片的完整路徑，例如 D:\\talks\\talk.mp4"
        spellCheck={false}
      />
      <button type="button" onClick={() => void browse()} disabled={busy}>
        選擇檔案
      </button>
      <button type="submit" className="primary" data-testid="import" disabled={busy || !trimmed}>
        匯入
      </button>
    </form>
  );
}
