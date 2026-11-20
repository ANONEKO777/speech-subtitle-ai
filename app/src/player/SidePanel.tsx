import { TriangleAlert, Undo2 } from "lucide-react";
import { type ReactNode, useState } from "react";
import type { LanguageInfo } from "../api/client";
import { EXPERIMENTAL, type Target } from "../api/targets";
import type { CueEditing } from "../editor/useCueEditing";
import { ExportMenu, type ExportAction } from "../export/ExportMenu";
import { type ExportItem, shortName } from "../export/exports";
import { SummaryView } from "../summary/SummaryView";
import type { Backend } from "../api/client";
import { AddTarget } from "./AddTarget";
import { CueList } from "./CueList";
import type { Cue, SubtitleMode } from "./cues";
import { type FailedKind, failureSummary } from "./failures";

export type Tab = "cues" | "summary" | "library" | "queue";

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly tab: Tab;
  readonly onTab: (tab: Tab) => void;
  readonly editing: CueEditing;
  readonly active: number;
  readonly mode: SubtitleMode;
  readonly marks: boolean;
  readonly languages: readonly LanguageInfo[];
  readonly lang: string;
  readonly onLang: (code: string) => void;
  /** The languages of `languages` that the backend has not judged. */
  readonly experimental: ReadonlySet<string>;
  /** The languages the video can still be translated into, and what picking one does. */
  readonly addable: readonly Target[];
  readonly onAddTarget: (code: string) => void;
  /** Why a language cannot be added now (a job is running on the project), or null. */
  readonly addBlocked: string | null;
  /** The cues of `lang` the translator could not do. */
  readonly failed: ReadonlyMap<number, FailedKind>;
  readonly summary: string | null | undefined;
  readonly summaryDegraded: boolean;
  readonly exports: readonly ExportItem[];
  readonly actions: readonly ExportAction[];
  readonly library: ReactNode;
  readonly batch: ReactNode;
  readonly batchBadge: string | null;
  readonly status: string | null;
  readonly onStatus: (message: string) => void;
  readonly onSeekCue: (cue: Cue) => void;
  readonly onSeekSeconds: (seconds: number) => void;
}

const TAB_LABEL: Record<Tab, string> = { cues: "字幕", summary: "摘要", library: "媒體庫", queue: "佇列" };

export function SidePanel(p: Props) {
  const { editing } = p;
  const [onlyFailed, setOnlyFailed] = useState(false);
  const target = shortName(p.languages.find((l) => l.code === p.lang)?.nativeName ?? p.lang);
  const { cues, edited, undo } = editing.state;
  const note = editing.failure ?? p.status;
  return (
    <aside className="side" data-testid="side-panel">
      <div className="side-head">
        <div className="tabs" role="tablist">
          {(["cues", "summary", "library", "queue"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              data-testid={`tab-${tab}`}
              aria-selected={p.tab === tab}
              onClick={() => p.onTab(tab)}
            >
              {TAB_LABEL[tab]}
              {tab === "queue" && p.batchBadge && (
                <span className="tab-badge" data-testid="queue-badge">
                  {p.batchBadge}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="side-tools">
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
          <ExportMenu backend={p.backend} projectId={p.projectId} items={p.exports} actions={p.actions} onResult={p.onStatus} />
        </div>
      </div>
      {(p.languages.length > 1 || p.addable.length > 0) && (
        <div className="side-langs" data-testid="side-langs">
          <span className="side-langs-label">字幕語言</span>
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
                  {p.experimental.has(l.code) ? `（${EXPERIMENTAL}）` : ""}
                </option>
              ))}
            </select>
          )}
          <AddTarget targets={p.addable} blocked={p.addBlocked} onAdd={p.onAddTarget} />
        </div>
      )}
      {p.tab === "cues" && p.failed.size > 0 && (
        <div className="failed-note" role="status" data-testid="failed-note" data-count={p.failed.size}>
          <TriangleAlert className="icon" aria-hidden />
          <span data-testid="failed-summary">{failureSummary(p.failed, target)}</span>
          <button type="button" className="ghost" data-testid="failed-filter" aria-pressed={onlyFailed} onClick={() => setOnlyFailed((v) => !v)}>
            {onlyFailed ? "顯示全部" : "只看這些"}
          </button>
        </div>
      )}
      {p.tab === "cues" ? (
        <CueList
          cues={cues}
          active={p.active}
          mode={p.mode}
          marks={p.marks}
          edited={edited}
          failed={p.failed}
          onlyFailed={onlyFailed && p.failed.size > 0}
          target={target}
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
          {p.tab === "library" ? (
            p.library
          ) : p.tab === "queue" ? (
            p.batch
          ) : p.summary === undefined ? null : (
            <>
              {p.summaryDegraded && (
                <p className="summary-notice" role="status" data-testid="summary-degraded">
                  這份摘要沒有通過語言檢查，可能夾雜錯字或其他語言的字，建議重新產生。
                </p>
              )}
              <SummaryView markdown={p.summary} onSeek={p.onSeekSeconds} />
            </>
          )}
        </div>
      )}
      <div className="side-foot" role="status" data-testid="side-status" data-has-note={note !== null}>
        {note ?? (edited.size > 0 ? `已修改 ${edited.size} 條，重新翻譯時會保留` : "按兩下字幕可以編輯")}
      </div>
    </aside>
  );
}
