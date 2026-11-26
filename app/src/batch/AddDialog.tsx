import { FileVideo, Folder, FolderOpen, ListPlus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { pickFolder, pickVideos } from "../api/backend";
import type { Backend, LanguageSet } from "../api/client";
import { type Detected, detectLine, hintFor, isDetection, preselect, switchLabel } from "../api/detect";
import { type SourceLang, type Unavailable, parseSourceLang, sourceNote } from "../api/sourceLang";
import { isExperimentalTarget, targetsFor, targetsOf } from "../api/targets";
import { useT } from "../i18n/I18nProvider";
import { SourceOptions } from "../import/ImportPanel";
import { useDetections } from "../import/useDetections";
import { type AddEntry, type Skipped, addToQueue } from "./api";
import { baseName, classifyPath } from "./paths";
import { TargetChoice } from "./TargetChoice";

interface Row extends AddEntry {
  readonly key: string;
  /** The person chose this row's language, so a guess does not replace it. */
  readonly touched?: boolean;
}

export const rowsFor = (paths: readonly string[], langs: readonly string[], source: SourceLang): AddEntry[] =>
  paths.map((path) =>
    classifyPath(path) === "folder" ? { path, langs, source, folder: { recursive: true } } : { path, langs, source },
  );

interface Props {
  readonly backend: Backend;
  readonly languages: LanguageSet;
  readonly initial: readonly AddEntry[];
  readonly onClose: () => void;
  readonly onAdded: (count: number) => void;
}

function SourceSelect({ value, unavailable, onChange, label, testid }: {
  value: SourceLang;
  unavailable: Unavailable;
  onChange: (code: SourceLang) => void;
  label: string;
  testid: string;
}) {
  return (
    <select className="lang-select" data-testid={testid} aria-label={label} value={value} onChange={(e) => onChange(parseSourceLang(e.target.value))}>
      <SourceOptions unavailable={unavailable} />
    </select>
  );
}

function RowDetect({ found, row, unavailable, onSwitch }: {
  found: Detected | undefined;
  row: Row;
  unavailable: Unavailable;
  onSwitch: (code: SourceLang) => void;
}) {
  const { t } = useT();
  if (found === "running") return <span className="add-detect" data-testid="add-row-detect" data-state="running">{t("detect.running")}</span>;
  if (!isDetection(found)) return null;
  const line = detectLine(found, t);
  if (line === null) return null;
  const hint = hintFor(found, row.source, unavailable, t);
  return (
    <span className="add-detect">
      <span data-testid="add-row-detect" data-state="done" data-detected={found.detected ?? ""}>
        {line}
      </span>
      {hint && (
        <span className="add-detect-hint" data-testid="add-row-hint">
          {hint.text}
          <button type="button" data-testid="add-row-switch" onClick={() => onSwitch(hint.switchTo)}>
            {switchLabel(hint.switchTo, t)}
          </button>
        </span>
      )}
    </span>
  );
}

export function AddDialog({ backend, languages, initial, onClose, onAdded }: Props) {
  const { t } = useT();
  const [defaultSource, setDefaultSource] = useState<SourceLang>(initial[0]?.source ?? "en");
  const [defaultLangs, setDefaultLangs] = useState<readonly string[]>(() =>
    targetsFor(languages, initial[0]?.source ?? "en", initial[0]?.langs ?? [languages.defaultCode]),
  );
  const [seq, setSeq] = useState(initial.length);
  const [rows, setRows] = useState<readonly Row[]>(() => initial.map((e, i) => ({ ...e, key: `r${i}` })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<readonly Skipped[]>([]);

  const notes = [
    ...new Set([defaultSource, ...rows.map((r) => r.source)].flatMap((code) => sourceNote(code, t) ?? [])),
    ...(rows.some((r) => r.langs.some((code) => isExperimentalTarget(languages, r.source, code)))
      ? [t("targets.experimentalHint")]
      : []),
  ];

  const append = (entries: readonly AddEntry[]) => {
    setRows((r) => {
      const have = new Set(r.map((x) => x.path));
      const fresh = entries.filter((e) => !have.has(e.path));
      return [...r, ...fresh.map((e, i) => ({ ...e, key: `r${seq + i}` }))];
    });
    setSeq((n) => n + entries.length);
  };
  const patch = (key: string, p: Partial<Row>) => setRows((r) => r.map((x) => (x.key === key ? { ...x, ...p } : x)));
  const setSource = (row: Row, source: SourceLang) => patch(row.key, { source, langs: targetsFor(languages, source, row.langs), touched: true });

  const found = useDetections(
    backend,
    rows.filter((r) => !r.folder).map((r) => r.path),
  );
  const preselected = useRef(new Set<string>());
  useEffect(() => {
    setRows((current) => {
      let changed = false;
      const next = current.map((row) => {
        const guess = found.get(row.path);
        if (row.folder || !isDetection(guess) || preselected.current.has(row.path)) return row;
        preselected.current.add(row.path);
        const code = preselect(guess, row.touched === true, languages.unavailable);
        if (code === null || code === row.source) return row;
        changed = true;
        return { ...row, source: code, langs: targetsFor(languages, code, row.langs) };
      });
      return changed ? next : current;
    });
  }, [found, languages]);

  async function addFiles() {
    append((await pickVideos()).map((path) => ({ path, langs: defaultLangs, source: defaultSource })));
  }
  async function addFolder() {
    const path = await pickFolder();
    if (path) append([{ path, langs: defaultLangs, source: defaultSource, folder: { recursive: true } }]);
  }
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await addToQueue(backend, rows);
      if (result.skipped.length === 0) {
        onAdded(result.added);
        onClose();
        return;
      }
      setSkipped(result.skipped);
      setRows([]);
      onAdded(result.added);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal" role="dialog" aria-label={t("batch.addTitle")} data-testid="add-dialog">
      <div className="modal-card add-card">
        <div className="overlay-head">
          <ListPlus className="icon" aria-hidden />
          <h2>{t("batch.addTitle")}</h2>
          <button type="button" className="ghost icon-button" aria-label={t("common.close")} data-testid="add-close" onClick={onClose}>
            <X className="icon" aria-hidden />
          </button>
        </div>
        <div className="add-tools">
          <button type="button" data-testid="add-files" onClick={() => void addFiles()}>
            <FolderOpen className="icon" aria-hidden />
            {t("batch.pickFiles")}
          </button>
          <button type="button" data-testid="add-folder" onClick={() => void addFolder()}>
            <Folder className="icon" aria-hidden />
            {t("batch.pickFolder")}
          </button>
          <span className="spacer" />
          <label className="add-lang">
            <span>{t("import.source")}</span>
            <SourceSelect
              value={defaultSource}
              unavailable={languages.unavailable}
              onChange={(source) => {
                setDefaultSource(source);
                setDefaultLangs((l) => targetsFor(languages, source, l));
              }}
              label={t("batch.defaultSource")}
              testid="add-default-source"
            />
          </label>
          <label className="add-lang">
            <span>{t("import.targetAria")}</span>
            <TargetChoice
              targets={targetsOf(languages, defaultSource)}
              value={defaultLangs}
              onChange={setDefaultLangs}
              label={t("batch.defaultTarget")}
              testid="add-default-lang"
            />
          </label>
          <button
            type="button"
            data-testid="add-apply-all"
            disabled={rows.length === 0}
            onClick={() => setRows((r) => r.map((x) => ({ ...x, langs: defaultLangs, source: defaultSource, touched: true })))}
          >
            {t("batch.applyAll")}
          </button>
        </div>
        {notes.length > 0 && (
          <p className="add-note" data-testid="add-source-note">
            {notes.join(" ")}
          </p>
        )}
        {rows.length === 0 ? (
          <p className="add-empty">{t("batch.addEmpty")}</p>
        ) : (
          <ul className="add-list" data-testid="add-list">
            {rows.map((row) => (
              <li key={row.key} data-testid="add-row">
                {row.folder ? <Folder className="icon" aria-hidden /> : <FileVideo className="icon" aria-hidden />}
                <span className="add-name" title={row.path}>
                  <b>{baseName(row.path) || row.path}</b>
                  <small>{row.path}</small>
                  {!row.folder && <RowDetect found={found.get(row.path)} row={row} unavailable={languages.unavailable} onSwitch={(code) => setSource(row, code)} />}
                </span>
                {row.folder && (
                  <label className="add-sub">
                    <input
                      type="checkbox"
                      checked={row.folder.recursive}
                      onChange={(e) => patch(row.key, { folder: { recursive: e.target.checked } })}
                    />
                    {t("batch.subfolders")}
                  </label>
                )}
                <SourceSelect
                  value={row.source}
                  unavailable={languages.unavailable}
                  onChange={(source) => setSource(row, source)}
                  label={t("import.source")}
                  testid="add-row-source"
                />
                <TargetChoice
                  targets={targetsOf(languages, row.source)}
                  value={row.langs}
                  onChange={(langs) => patch(row.key, { langs })}
                  label={t("import.targetAria")}
                  testid="add-row-lang"
                />
                <button
                  type="button"
                  className="ghost icon-button"
                  aria-label={t("batch.action.remove")}
                  onClick={() => setRows((r) => r.filter((x) => x.key !== row.key))}
                >
                  <X className="icon" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {skipped.length > 0 && (
          <ul className="add-skipped" data-testid="add-skipped">
            {skipped.map((s) => (
              <li key={s.path}>
                <b>{baseName(s.path)}</b>
                {t("batch.skippedSep")}
                {s.reason}
              </li>
            ))}
          </ul>
        )}
        {error && (
          <p className="error" role="alert" data-testid="add-error">
            {error}
          </p>
        )}
        <div className="add-foot">
          <button type="button" className="ghost" onClick={onClose}>
            {skipped.length > 0 ? t("common.close") : t("common.cancel")}
          </button>
          <button type="button" className="primary" data-testid="add-submit" disabled={busy || rows.length === 0} onClick={() => void submit()}>
            <ListPlus className="icon" aria-hidden />
            {rows.length > 0 ? t("batch.addSubmitCount", { n: rows.length }) : t("batch.addTitle")}
          </button>
        </div>
      </div>
    </div>
  );
}
