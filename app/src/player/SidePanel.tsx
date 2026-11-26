import { TriangleAlert, Undo2 } from "lucide-react";
import { type ReactNode, useState } from "react";
import type { LanguageInfo } from "../api/client";
import type { Target } from "../api/targets";
import type { CueEditing } from "../editor/useCueEditing";
import { ExportMenu, type ExportAction } from "../export/ExportMenu";
import type { ExportItem } from "../export/exports";
import { useT } from "../i18n/I18nProvider";
import { SummaryView } from "../summary/SummaryView";
import type { Backend } from "../api/client";
import { AddTarget } from "./AddTarget";
import { CueList } from "./CueList";
import type { Cue, SubtitleMode } from "./cues";
import { type FailedKind, failureSummary } from "./failures";
import { languageLabel } from "./langName";

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


export function SidePanel(p: Props) {
  const { t, plural, locale } = useT();
  const { editing } = p;
  const [onlyFailed, setOnlyFailed] = useState(false);
  const shown = p.languages.find((l) => l.code === p.lang);
  const target = shown ? languageLabel(shown, locale) : p.lang;
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
              {t(`player.tab.${tab}`)}
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
            title={t("player.undoTitle")}
            aria-label={t("player.undo")}
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
          <span className="side-langs-label">{t("player.langs")}</span>
          {p.languages.length > 1 && (
            <select
              className="lang-select"
              data-testid="lang-select"
              aria-label={t("player.langShown")}
              title={p.languages.find((l) => l.code === p.lang)?.name}
              value={p.lang}
              onChange={(e) => p.onLang(e.target.value)}
            >
              {p.languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {p.experimental.has(l.code) ? t("import.targetExperimental", { name: languageLabel(l, locale) }) : languageLabel(l, locale)}
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
          <span data-testid="failed-summary">{failureSummary(p.failed, target, { t, plural })}</span>
          <button type="button" className="ghost" data-testid="failed-filter" aria-pressed={onlyFailed} onClick={() => setOnlyFailed((v) => !v)}>
            {onlyFailed ? t("player.failedShowAll") : t("player.failedOnly")}
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
                  {t("player.summaryDegraded")}
                </p>
              )}
              <SummaryView markdown={p.summary} onSeek={p.onSeekSeconds} />
            </>
          )}
        </div>
      )}
      <div className="side-foot" role="status" data-testid="side-status" data-has-note={note !== null}>
        {note ?? (edited.size > 0 ? plural("player.foot.edited", edited.size) : t("player.foot.hint"))}
      </div>
    </aside>
  );
}
