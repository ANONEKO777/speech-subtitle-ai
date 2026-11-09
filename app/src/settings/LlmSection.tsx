import { CircleCheck, Cloud, ShieldAlert, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, type Backend } from "../api/client";
import { fetchSettings, saveLlm, testLlm } from "../manage/api";
import type { LlmSaved, LlmSource, LlmTest, SettingsView } from "../manage/types";
import { type LlmDraft, draftFrom, toBody, validateLlm } from "./llm";

export const CLOUD_NOTICE = "選擇雲端 LLM 後，影片的逐字稿與翻譯內容會傳送到你填寫的雲端服務，離開這台電腦。請確認你信任這個服務，且影片內容允許外傳。";

const SOURCES: readonly { id: LlmSource; label: string; hint: string }[] = [
  { id: "builtin", label: "內建 llama-server", hint: "全程在本機執行，不連網。" },
  { id: "ollama", label: "Ollama", hint: "連到你自己的 Ollama，通常也在本機。" },
  { id: "cloud", label: "雲端服務", hint: "OpenAI 相容的網址與金鑰。內容會離開這台電腦。" },
];

function Field({ label, error, children, id }: { label: string; error: string | undefined; children: React.ReactNode; id: string }) {
  return (
    <div className="field-row">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {children}
      {error && (
        <p className="note warn" data-testid={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}

export function LlmSection({ backend }: { backend: Backend }) {
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [draft, setDraft] = useState<LlmDraft | null>(null);
  const [result, setResult] = useState<LlmTest | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await fetchSettings(backend);
      setSettings(s);
      setDraft(draftFrom(s.llm));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [backend]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!settings || !draft) {
    return (
      <section className="panel" data-testid="llm-section">
        {error && (
          <p className="note bad" role="alert">
            {error}
          </p>
        )}
      </section>
    );
  }

  const savedLlm: LlmSaved = settings.llm;
  const check = validateLlm(draft, savedLlm);
  const set = (patch: Partial<LlmDraft>) => {
    setDraft({ ...draft, ...patch });
    setSaved(false);
    setResult(null);
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await testLlm(backend, toBody(draft)));
    } catch (e) {
      setResult({ ok: false, url: "", detail: e instanceof ApiError ? e.message : String(e), models: [] });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const s = await saveLlm(backend, toBody(draft));
      setSettings(s);
      setDraft(draftFrom(s.llm));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const cloud = draft.source === "cloud";
  return (
    <section className="panel" data-testid="llm-section" aria-labelledby="llm-title">
      <div className="panel-head">
        <div>
          <h2 id="llm-title">LLM 來源</h2>
          <p className="muted" data-testid="llm-current">
            目前使用：{SOURCES.find((s) => s.id === savedLlm.source)?.label}
            {savedLlm.source === "cloud" ? "（雲端，內容會離開這台電腦）" : ""}
          </p>
        </div>
      </div>

      {settings.problem && (
        <p className="note bad" role="alert">
          設定檔有問題：{settings.problem}
        </p>
      )}

      <div className="card manage-card">
        <div className="source-choices" role="radiogroup" aria-label="LLM 來源">
          {SOURCES.map((s) => (
            <button
              key={s.id}
              type="button"
              role="radio"
              aria-checked={draft.source === s.id}
              className="source-choice"
              data-testid={`llm-source-${s.id}`}
              onClick={() => set({ source: s.id })}
            >
              <strong>{s.label}</strong>
              <span className="sub">{s.hint}</span>
            </button>
          ))}
        </div>

        {draft.source === "ollama" && (
          <div className="fields">
            <Field id="ollama-url" label="Ollama 網址" error={check.errors.ollamaUrl}>
              <input id="ollama-url" className="text-input" data-testid="ollama-url" value={draft.ollamaUrl} onChange={(e) => set({ ollamaUrl: e.target.value })} />
            </Field>
            <Field id="ollama-model" label="模型名稱" error={check.errors.ollamaModel}>
              <input
                id="ollama-model"
                className="text-input"
                data-testid="ollama-model"
                list="llm-models"
                placeholder="例如 qwen3:8b"
                value={draft.ollamaModel}
                onChange={(e) => set({ ollamaModel: e.target.value })}
              />
            </Field>
          </div>
        )}

        {cloud && (
          <div className="fields">
            <div className="callout warn" role="note" data-testid="cloud-warning">
              <ShieldAlert className="icon" aria-hidden />
              <div>
                <p>
                  <strong>內容會離開這台電腦</strong>
                </p>
                <p>{CLOUD_NOTICE}</p>
              </div>
            </div>
            <Field id="cloud-url" label="服務網址" error={check.errors.cloudUrl}>
              <input
                id="cloud-url"
                className="text-input"
                data-testid="cloud-url"
                placeholder="https://api.example.com/v1"
                value={draft.cloudUrl}
                onChange={(e) => set({ cloudUrl: e.target.value })}
              />
            </Field>
            <Field id="cloud-model" label="模型名稱" error={check.errors.cloudModel}>
              <input id="cloud-model" className="text-input" data-testid="cloud-model" list="llm-models" value={draft.cloudModel} onChange={(e) => set({ cloudModel: e.target.value })} />
            </Field>
            <Field id="cloud-key" label="API 金鑰（只能寫入，儲存後不會再顯示）" error={check.errors.apiKey}>
              <input
                id="cloud-key"
                className="text-input"
                type="password"
                autoComplete="off"
                data-testid="cloud-key"
                placeholder={savedLlm.apiKeySet ? "已儲存金鑰；要更換再輸入" : "貼上 API 金鑰"}
                value={draft.apiKey}
                onChange={(e) => set({ apiKey: e.target.value })}
              />
            </Field>
            <label className="consent" data-testid="cloud-consent-row">
              <input type="checkbox" data-testid="cloud-consent" checked={draft.consent} onChange={(e) => set({ consent: e.target.checked })} />
              <span>我了解影片內容會傳送到上面的雲端服務，並同意儲存這個設定。</span>
            </label>
            {check.errors.consent && (
              <p className="note warn" data-testid="cloud-consent-error">
                {check.errors.consent}
              </p>
            )}
          </div>
        )}

        <datalist id="llm-models">
          {(result?.models ?? []).map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>

        <div className="dialog-buttons start">
          <button type="button" data-testid="llm-test" disabled={testing || !check.canTest} onClick={() => void test()}>
            {testing ? "測試中…" : "測試連線"}
          </button>
          <button type="button" className="primary" data-testid="llm-save" disabled={saving || !check.canSave} onClick={() => void save()}>
            儲存
          </button>
        </div>

        {result && (
          <div className={`callout ${result.ok ? "ok" : "bad"}`} role="status" data-testid="llm-test-result" data-ok={result.ok}>
            {result.ok ? <CircleCheck className="icon" aria-hidden /> : <TriangleAlert className="icon" aria-hidden />}
            <div>
              <p>
                <strong>{result.ok ? "連線成功" : "連線失敗"}</strong>
              </p>
              {result.url && (
                <p>
                  網址：<code data-testid="llm-test-url">{result.url}</code>
                </p>
              )}
              <p data-testid="llm-test-detail">{result.detail}</p>
              {result.models.length > 0 && <p className="sub">可用的模型：{result.models.slice(0, 8).join("、")}</p>}
            </div>
          </div>
        )}
        {error && (
          <p className="note bad" role="alert" data-testid="llm-save-error">
            <Cloud className="icon" aria-hidden />
            {error}
          </p>
        )}
        {saved && (
          <p className="note ok" role="status" data-testid="llm-saved">
            已儲存。
          </p>
        )}
      </div>
    </section>
  );
}
