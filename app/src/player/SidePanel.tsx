import { Undo2 } from "lucide-react";
import type { LanguageInfo } from "../api/client";
import type { CueEditing } from "../editor/useCueEditing";
import { ExportMenu } from "../export/ExportMenu";
import { type ExportItem, shortName } from "../export/exports";
import { SummaryView } from "../summary/SummaryView";
import type { Backend } from "../api/client";
import { CueList } from "./CueList";
import type { Cue, SubtitleMode } from "./cues";

export type Tab = "cues" | "summary";

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly tab: Tab;
  readonly onTab: (tab: Tab) => void;
  readonly editing: CueEditing;
  readonly active: number;
  readonly mode: SubtitleMode;
  readonly languages: readonly LanguageInfo[];
  readonly lang: string;
  readonly onLang: (code: string) => void;
  readonly summary: string | null | undefined;
  readonly exports: readonly ExportItem[];
  readonly status: string | null;
  readonly onStatus: (message: string) => void;
  readonly onSeekCue: (cue: Cue) => void;
  readonly onSeekSeconds: (seconds: number) => void;
}

export function SidePanel(p: Props) {
  const { editing } = p;
  const { cues, edited, undo } = editing.state;
  const note = editing.failure ?? p.status;
  return (
    <aside className="side" data-testid="side-panel">
      <div className="side-head">
        <div className="tabs" role="tablist">
          {(["cues", "summary"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              data-testid={`tab-${tab}`}
              aria-selected={p.tab === tab}
              onClick={() => p.onTab(tab)}
            >
              {tab === "cues" ? "字幕" : "摘要"}
            </button>
          ))}
        </div>
        <div className="side-tools">
          {p.languages.length > 1 && (
            <select
              className="lang-select"
              data-testid="lang-select"
              aria-label="顯示的語言"
              title={p.languages.find((l) => l.code === p.lang)?.name}
              value={p.lang}
              onChange={(e) => p.onLang(e.target.value)}
            >
              {p.languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {shortName(l.nativeName)}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="ghost icon-button"
            data-testid="undo"
            title="復原上一次修改 (Ctrl+Z)"
            aria-label="復原上一次修改"
            disabled={undo.length === 0}
            onClick={() => void editing.undo()}
          >
            <Undo2 className="icon" aria-hidden />
          </button>
          <ExportMenu backend={p.backend} projectId={p.projectId} items={p.exports} onResult={p.onStatus} />
        </div>
      </div>
      {p.tab === "cues" ? (
        <CueList
          cues={cues}
          active={p.active}
          mode={p.mode}
          edited={edited}
          editingId={editing.editingId}
          editor={(cue) => ({
            validate: (draft) => editing.validate(cue.id, draft),
            refusal: editing.refusal,
            onCommit: (draft) => editing.commit(cue.id, draft),
            onCancel: editing.cancel,
          })}
          onSeek={p.onSeekCue}
          onEdit={editing.begin}
        />
      ) : (
        <div className="side-body">
          {p.summary === undefined ? null : <SummaryView markdown={p.summary} onSeek={p.onSeekSeconds} />}
        </div>
      )}
      <div className="side-foot" role="status" data-testid="side-status" data-has-note={note !== null}>
        {note ?? (edited.size > 0 ? `已修改 ${edited.size} 條，重新翻譯時會保留` : "按兩下字幕可以編輯")}
      </div>
    </aside>
  );
}
