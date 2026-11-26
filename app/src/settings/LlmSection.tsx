import { CircleCheck, Cloud, ShieldAlert, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, type Backend } from "../api/client";
import type { PlainKey } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import { fetchSettings, saveLlm, testLlm } from "../manage/api";
import type { LlmSaved, LlmSource, LlmTest, SettingsView } from "../manage/types";
import { type LlmDraft, draftFrom, toBody, validateLlm } from "./llm";

const SOURCES: readonly { id: LlmSource; label: PlainKey; hint: PlainKey }[] = [
  { id: "builtin", label: "llm.builtin", hint: "llm.builtinHint" },
  { id: "ollama", label: "llm.ollama", hint: "llm.ollamaHint" },
  { id: "cloud", label: "llm.cloud", hint: "llm.cloudHint" },
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
  const { t } = useT();
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
  const check = validateLlm(draft, savedLlm, t);
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
          <h2 id="llm-title">{t("llm.title")}</h2>
          <p className="muted" data-testid="llm-current">
            {t("llm.current", { source: t(SOURCES.find((s) => s.id === savedLlm.source)?.label ?? "llm.builtin") })}
            {savedLlm.source === "cloud" ? t("llm.currentCloud") : ""}
          </p>
        </div>
      </div>

      {settings.problem && (
        <p className="note bad" role="alert">
          {t("llm.problem", { problem: settings.problem })}
        </p>
      )}

      <div className="card manage-card">
        <div className="source-choices" role="radiogroup" aria-label={t("llm.title")}>
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
              <strong>{t(s.label)}</strong>
              <span className="sub">{t(s.hint)}</span>
            </button>
          ))}
        </div>

        {draft.source === "ollama" && (
          <div className="fields">
            <Field id="ollama-url" label={t("llm.ollamaUrl")} error={check.errors.ollamaUrl}>
              <input id="ollama-url" className="text-input" data-testid="ollama-url" value={draft.ollamaUrl} onChange={(e) => set({ ollamaUrl: e.target.value })} />
            </Field>
            <Field id="ollama-model" label={t("llm.modelName")} error={check.errors.ollamaModel}>
              <input
                id="ollama-model"
                className="text-input"
                data-testid="ollama-model"
                list="llm-models"
                placeholder={t("llm.modelPlaceholder")}
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
                  <strong>{t("llm.leavesTitle")}</strong>
                </p>
                <p>{t("llm.cloudNotice")}</p>
              </div>
            </div>
            <Field id="cloud-url" label={t("llm.serviceUrl")} error={check.errors.cloudUrl}>
              <input
                id="cloud-url"
                className="text-input"
                data-testid="cloud-url"
                placeholder="https://api.example.com/v1"
                value={draft.cloudUrl}
                onChange={(e) => set({ cloudUrl: e.target.value })}
              />
            </Field>
            <Field id="cloud-model" label={t("llm.modelName")} error={check.errors.cloudModel}>
              <input id="cloud-model" className="text-input" data-testid="cloud-model" list="llm-models" value={draft.cloudModel} onChange={(e) => set({ cloudModel: e.target.value })} />
            </Field>
            <Field id="cloud-key" label={t("llm.apiKey")} error={check.errors.apiKey}>
              <input
                id="cloud-key"
                className="text-input"
                type="password"
                autoComplete="off"
                data-testid="cloud-key"
                placeholder={savedLlm.apiKeySet ? t("llm.keySaved") : t("llm.keyPaste")}
                value={draft.apiKey}
                onChange={(e) => set({ apiKey: e.target.value })}
              />
            </Field>
            <label className="consent" data-testid="cloud-consent-row">
              <input type="checkbox" data-testid="cloud-consent" checked={draft.consent} onChange={(e) => set({ consent: e.target.checked })} />
              <span>{t("llm.consent")}</span>
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
            {testing ? t("llm.testing") : t("llm.test")}
          </button>
          <button type="button" className="primary" data-testid="llm-save" disabled={saving || !check.canSave} onClick={() => void save()}>
            {t("llm.save")}
          </button>
        </div>

        {result && (
          <div className={`callout ${result.ok ? "ok" : "bad"}`} role="status" data-testid="llm-test-result" data-ok={result.ok}>
            {result.ok ? <CircleCheck className="icon" aria-hidden /> : <TriangleAlert className="icon" aria-hidden />}
            <div>
              <p>
                <strong>{result.ok ? t("llm.testOk") : t("llm.testFailed")}</strong>
              </p>
              {result.url && (
                <p>
                  {t("llm.url")}<code data-testid="llm-test-url">{result.url}</code>
                </p>
              )}
              <p data-testid="llm-test-detail">{result.detail}</p>
              {result.models.length > 0 && <p className="sub">{t("llm.models", { models: result.models.slice(0, 8).join(t("common.listSeparator")) })}</p>}
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
            {t("llm.saved")}
          </p>
        )}
      </div>
    </section>
  );
}
