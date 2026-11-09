import { FileVideo, Folder, FolderOpen, ListPlus, X } from "lucide-react";
import { useState } from "react";
import { pickFolder, pickVideos } from "../api/backend";
import type { Backend, LanguageSet } from "../api/client";
import { type AddEntry, type Skipped, addToQueue } from "./api";
import { isExperimental } from "./lang";
import { baseName, classifyPath } from "./paths";

interface Row extends AddEntry {
  readonly key: string;
}

export const rowsFor = (paths: readonly string[], lang: string): AddEntry[] =>
  paths.map((path) =>
    classifyPath(path) === "folder" ? { path, lang, folder: { recursive: true } } : { path, lang },
  );

interface Props {
  readonly backend: Backend;
  readonly languages: LanguageSet;
  readonly initial: readonly AddEntry[];
  readonly onClose: () => void;
  readonly onAdded: (count: number) => void;
}

function LangSelect({ value, set, onChange, label, testid }: {
  value: string;
  set: LanguageSet;
  onChange: (code: string) => void;
  label: string;
  testid: string;
}) {
  return (
    <select className="lang-select" data-testid={testid} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {set.languages.map((l) => (
        <option key={l.code} value={l.code}>
          {l.nativeName}
          {l.quality === "experimental" ? "（實驗性）" : ""}
        </option>
      ))}
    </select>
  );
}

export function AddDialog({ backend, languages, initial, onClose, onAdded }: Props) {
  const [defaultLang, setDefaultLang] = useState(languages.defaultCode);
  const [seq, setSeq] = useState(initial.length);
  const [rows, setRows] = useState<readonly Row[]>(() => initial.map((e, i) => ({ ...e, key: `r${i}` })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<readonly Skipped[]>([]);

  const append = (entries: readonly AddEntry[]) => {
    setRows((r) => {
      const have = new Set(r.map((x) => x.path));
      const fresh = entries.filter((e) => !have.has(e.path));
      return [...r, ...fresh.map((e, i) => ({ ...e, key: `r${seq + i}` }))];
    });
    setSeq((n) => n + entries.length);
  };
  const patch = (key: string, p: Partial<AddEntry>) => setRows((r) => r.map((x) => (x.key === key ? { ...x, ...p } : x)));

  async function addFiles() {
    append((await pickVideos()).map((path) => ({ path, lang: defaultLang })));
  }
  async function addFolder() {
    const path = await pickFolder();
    if (path) append([{ path, lang: defaultLang, folder: { recursive: true } }]);
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
    <div className="modal" role="dialog" aria-label="加入佇列" data-testid="add-dialog">
      <div className="modal-card add-card">
        <div className="overlay-head">
          <ListPlus className="icon" aria-hidden />
          <h2>加入佇列</h2>
          <button type="button" className="ghost icon-button" aria-label="關閉" data-testid="add-close" onClick={onClose}>
            <X className="icon" aria-hidden />
          </button>
        </div>
        <div className="add-tools">
          <button type="button" data-testid="add-files" onClick={() => void addFiles()}>
            <FolderOpen className="icon" aria-hidden />
            選擇多個檔案
          </button>
          <button type="button" data-testid="add-folder" onClick={() => void addFolder()}>
            <Folder className="icon" aria-hidden />
            選擇資料夾
          </button>
          <span className="spacer" />
          <label className="add-lang">
            <span>預設語言</span>
            <LangSelect value={defaultLang} set={languages} onChange={setDefaultLang} label="預設語言" testid="add-default-lang" />
          </label>
          <button
            type="button"
            data-testid="add-apply-all"
            disabled={rows.length === 0}
            onClick={() => setRows((r) => r.map((x) => ({ ...x, lang: defaultLang })))}
          >
            套用到全部
          </button>
        </div>
        {rows.length === 0 ? (
          <p className="add-empty">選擇影片檔或資料夾，也可以直接把多個檔案拖到視窗上。</p>
        ) : (
          <ul className="add-list" data-testid="add-list">
            {rows.map((row) => (
              <li key={row.key} data-testid="add-row">
                {row.folder ? <Folder className="icon" aria-hidden /> : <FileVideo className="icon" aria-hidden />}
                <span className="add-name" title={row.path}>
                  <b>{baseName(row.path) || row.path}</b>
                  <small>{row.path}</small>
                </span>
                {row.folder && (
                  <label className="add-sub">
                    <input
                      type="checkbox"
                      checked={row.folder.recursive}
                      onChange={(e) => patch(row.key, { folder: { recursive: e.target.checked } })}
                    />
                    含子資料夾
                  </label>
                )}
                <LangSelect value={row.lang} set={languages} onChange={(lang) => patch(row.key, { lang })} label="目標語言" testid="add-row-lang" />
                {isExperimental(row.lang, languages.languages) && <span className="chip-exp">實驗性</span>}
                <button
                  type="button"
                  className="ghost icon-button"
                  aria-label="移除"
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
                <b>{baseName(s.path)}</b>：{s.reason}
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
            {skipped.length > 0 ? "關閉" : "取消"}
          </button>
          <button type="button" className="primary" data-testid="add-submit" disabled={busy || rows.length === 0} onClick={() => void submit()}>
            <ListPlus className="icon" aria-hidden />
            加入佇列{rows.length > 0 ? `（${rows.length}）` : ""}
          </button>
        </div>
      </div>
    </div>
  );
}
