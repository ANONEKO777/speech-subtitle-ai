import { CircleCheck, Cloud, Cpu, LoaderCircle, MemoryStick, TriangleAlert, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { Backend } from "../api/client";
import { type Translate, tZhTW } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import { cancelDownload, chooseProfile, downloadProfileAssets, fetchLastSelfTest, fetchProfile, runSelfTest } from "../manage/api";
import { isActive, overall } from "../manage/downloads";
import { bytes, mib } from "../manage/format";
import { chipOrGpu, deviceLabel, isCpuProfile, isMac } from "../manage/hardwareText";
import { JobRow } from "../manage/JobRow";
import { localBuildText, toBuild, toDownload } from "../manage/localBuild";
import { profileBlurb, profileName } from "../manage/profileText";
import type { Downloads } from "../manage/useDownloads";
import type { ProfileId, ProfileOption, ProfileView, SelfTest } from "../manage/types";

/** The notice under a processor-only profile. A Mac has no NVIDIA card to be missing and its GPU is Metal, so it says what this profile gives up. */
export const cpuNotice = (id: ProfileId, t: Translate = tZhTW): string =>
  t(id === "apple-cpu" ? "hw.cpuNotice.apple" : "hw.cpuNotice.cpu", { advice: t("hw.cloudAdvice") });

export function selfTestText(result: SelfTest, t: Translate = tZhTW): { tone: "ok" | "warn" | "bad"; title: string; body: string } {
  if (result.ok && result.fallback) return { tone: "warn", title: t("selftest.fellBack"), body: result.fallback.reason };
  if (result.ok) return { tone: "ok", title: t("selftest.passed", { device: deviceLabel(result.device, t) }), body: t("selftest.seconds", { seconds: result.seconds.toFixed(1) }) };
  return { tone: "bad", title: t("selftest.failed"), body: result.message };
}

export function SelfTestPanel({ result, running }: { result: SelfTest | null; running: boolean }) {
  const { t } = useT();
  if (running) {
    return (
      <p className="note" data-testid="selftest-running">
        <LoaderCircle className="icon spin" aria-hidden />
        {t("selftest.running")}
      </p>
    );
  }
  if (!result) return null;
  const text = selfTestText(result, t);
  return (
    <div className={`callout ${text.tone}`} data-testid="selftest-result" data-ok={result.ok} data-device={result.device} data-fallback={result.fallback !== null}>
      {text.tone === "ok" ? <CircleCheck className="icon" aria-hidden /> : <TriangleAlert className="icon" aria-hidden />}
      <div>
        <p>
          <strong data-testid="selftest-title">{text.title}</strong>
        </p>
        <p data-testid="selftest-body">{text.body}</p>
        {result.stages.length > 0 && (
          <ul className="stages">
            {result.stages.map((s) => (
              <li key={`${s.stage}-${s.device}`} data-ok={s.ok}>
                {t("selftest.stageLine", {
                  stage: s.stage === "asr" ? t("selftest.stage.asr") : "LLM",
                  runtime: s.runtimeId,
                  device: s.device,
                  status: s.ok ? t("selftest.stage.ok") : t("selftest.stage.failed"),
                  seconds: s.seconds.toFixed(1),
                })}
                {s.ok ? "" : t("selftest.stageDetail", { detail: s.detail })}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function missingText(option: ProfileOption, { t, plural }: Pick<ReturnType<typeof useT>, "t" | "plural">): string {
  if (option.missing.length === 0) return t("hw.optionComplete");
  const get = toDownload(option.missing);
  const build = toBuild(option.missing);
  const download = plural("hw.optionMissing", get.length, { size: bytes(option.downloadBytes) });
  if (build.length === 0) return download;
  const built = t("hw.optionBuild", { n: build.length, how: localBuildText(t) });
  return get.length === 0 ? built : t("hw.optionBoth", { download, built });
}

interface Props {
  readonly backend: Backend;
  readonly downloads: Downloads;
  readonly onOpenLlm: () => void;
}

export function HardwareSection({ backend, downloads, onOpenLlm }: Props) {
  const texts = useT();
  const { t, plural } = texts;
  const [view, setView] = useState<ProfileView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switched, setSwitched] = useState<{ readonly id: ProfileId; readonly warnings: readonly string[]; readonly jobIds: readonly string[] } | null>(null);
  const [test, setTest] = useState<SelfTest | null>(null);
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setView(await fetchProfile(backend));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [backend]);

  useEffect(() => {
    void load();
    void fetchLastSelfTest(backend).then(setTest, () => undefined);
  }, [backend, load]);

  const endedKey = downloads.list.filter((j) => !isActive(j)).map((j) => `${j.id}:${j.state}`).join(",");
  useEffect(() => {
    void load();
  }, [endedKey, load]);

  const choose = async (profile: ProfileId | null) => {
    setBusy(true);
    setError(null);
    try {
      const change = await chooseProfile(backend, profile);
      setView(change.profile);
      setSwitched({ id: change.profile.active.id, warnings: change.warnings, jobIds: [] });
      setTest(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const fetchMissing = async () => {
    setError(null);
    try {
      const jobs = await downloadProfileAssets(backend);
      setSwitched((s) => (s ? { ...s, jobIds: jobs.map((j) => j.id) } : s));
      downloads.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const selfTest = async () => {
    setTesting(true);
    setError(null);
    try {
      setTest(await runSelfTest(backend));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  const hw = view?.hardware;
  const active = view?.profiles.find((p) => p.active);
  const jobs = downloads.list.filter((j) => switched?.jobIds.includes(j.id));
  const total = overall(jobs);
  const first = hw ? chipOrGpu(hw, t) : null;
  return (
    <section className="panel" data-testid="hardware-section" aria-labelledby="hw-title">
      <div className="panel-head">
        <div>
          <h2 id="hw-title">{t("hw.title")}</h2>
          <p className="muted">{t("hw.hint")}</p>
        </div>
      </div>

      {error && (
        <p className="note bad" role="alert" data-testid="hw-error">
          {error}
        </p>
      )}

      {hw && view && (
        <>
          <div className="card manage-card">
            <h3>{t("hw.detected")}</h3>
            <dl className="facts">
              <div>
                <dt>{first?.label}</dt>
                <dd data-testid="hw-gpu">{first?.value}</dd>
              </div>
              {!isMac(hw) && (
                <>
                  <div>
                    <dt>{t("hw.vram")}</dt>
                    <dd data-testid="hw-vram">{mib(hw.vramMib)}</dd>
                  </div>
                  <div>
                    <dt>{t("hw.driver")}</dt>
                    <dd data-testid="hw-driver">{hw.driverVersion ?? "—"}</dd>
                  </div>
                </>
              )}
              <div>
                <dt>{isMac(hw) ? t("hw.unifiedMemory") : t("hw.memory")}</dt>
                <dd data-testid="hw-ram">{mib(hw.ramMib)}</dd>
              </div>
              <div>
                <dt>{t("hw.disk")}</dt>
                <dd data-testid="hw-disk">{mib(hw.diskFreeMib)}</dd>
              </div>
            </dl>
            <p data-testid="hw-recommended">
              {t("hw.recommended")}
              <strong>{profileName(view.recommended.id, t)}</strong>
            </p>
            <details>
              <summary>{t("hw.why")}</summary>
              <pre className="why">{view.recommended.why}</pre>
            </details>
          </div>

          <div className="profiles" role="radiogroup" aria-label={t("hw.profiles")} data-testid="profiles">
            {view.profiles.map((p) => (
              <div
                key={p.id}
                className="card profile-card"
                role="radio"
                aria-checked={p.active}
                data-testid={`profile-${p.id}`}
                data-active={p.active}
                data-recommended={p.recommended}
              >
                <div className="profile-title">
                  {isCpuProfile(p.id) ? <Cpu className="icon" aria-hidden /> : <Zap className="icon" aria-hidden />}
                  <strong>{profileName(p.id, t)}</strong>
                </div>
                <p className="sub">{profileBlurb(p.id, t)}</p>
                <div className="chips">
                  {p.active && <span className="chip-tag on">{t("hw.inUse")}</span>}
                  {p.recommended && <span className="chip-tag rec">{t("hw.recommendedTag")}</span>}
                  {!p.fitsHardware && <span className="chip-tag warn">{t("hw.mayNotFit")}</span>}
                </div>
                <p className="sub" data-testid={`profile-${p.id}-missing`}>
                  {missingText(p, texts)}
                </p>
                {p.recommendCloud && (
                  <p className="note cloud" data-testid="cpu-cloud-note">
                    <Cloud className="icon" aria-hidden />
                    {cpuNotice(p.id, t)}
                  </p>
                )}
                <button type="button" className={p.active ? "ghost" : "primary"} data-testid={`profile-use-${p.id}`} disabled={p.active || busy} onClick={() => void choose(p.id)}>
                  {p.active ? t("hw.useActive") : t("hw.use")}
                </button>
              </div>
            ))}
          </div>

          {view.active.source === "user" && (
            <button type="button" className="ghost link" data-testid="profile-auto" disabled={busy} onClick={() => void choose(null)}>
              {t("hw.auto")}
            </button>
          )}
          {active?.recommendCloud && (
            <button type="button" className="ghost link" data-testid="goto-llm" onClick={onOpenLlm}>
              {t("hw.gotoLlm")}
            </button>
          )}

          {switched && (
            <div className="callout" data-testid="switch-result" data-profile={switched.id}>
              <MemoryStick className="icon" aria-hidden />
              <div>
                <p>
                  {t("hw.switched.pre")}
                  <strong>{profileName(switched.id, t)}</strong>
                  {t("hw.switched.post")}
                </p>
                {switched.warnings.map((w) => (
                  <p key={w} className="note warn" data-testid="switch-warning">
                    {w}
                  </p>
                ))}
                {active && active.missing.length > 0 ? (
                  <>
                    <p data-testid="switch-missing-title">
                      {toDownload(active.missing).length > 0
                        ? plural("hw.missingTitle", toDownload(active.missing).length, { size: bytes(active.downloadBytes) })
                        : t("hw.missingBuildTitle")}
                    </p>
                    <ul className="stages" data-testid="switch-missing">
                      {active.missing.map((m) => (
                        <li key={m.id}>
                          {t("hw.missingItem", { id: m.id, kind: m.type === "model" ? t("asset.model") : t("asset.program"), what: m.localBuild ? localBuildText(t) : bytes(m.sizeBytes) })}
                        </li>
                      ))}
                    </ul>
                    {jobs.length === 0 && toDownload(active.missing).length > 0 && (
                      <button type="button" className="primary" data-testid="switch-download" onClick={() => void fetchMissing()}>
                        {t("hw.download")}
                      </button>
                    )}
                  </>
                ) : (
                  <p data-testid="switch-complete">{t("hw.complete")}</p>
                )}
                {jobs.length > 0 && (
                  <div className="jobs" data-testid="switch-jobs">
                    {jobs.map((j) => (
                      <JobRow key={j.id} job={j} testId={`switch-job-${j.assetId}`} />
                    ))}
                    {jobs.some(isActive) && (
                      <p className="sub" data-testid="switch-overall">
                        {t("hw.overall", { percent: Math.round(total.fraction * 100) })}
                        <button type="button" className="ghost" onClick={() => jobs.filter(isActive).forEach((j) => void cancelDownload(backend, j.id))}>
                          {t("hw.cancelAll")}
                        </button>
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="card manage-card">
            <h3>{t("hw.selfTest")}</h3>
            <p className="muted">{t("hw.selfTestHint")}</p>
            {view.fallback && !test && (
              <p className="note warn" data-testid="fallback-banner">
                {t("hw.fallback", { reason: view.fallback.reason })}
              </p>
            )}
            <button type="button" data-testid="selftest-run" disabled={testing} onClick={() => void selfTest()}>
              {testing ? t("hw.selfTestRunning") : t("hw.selfTestRun")}
            </button>
            <SelfTestPanel result={test} running={testing} />
          </div>
        </>
      )}
    </section>
  );
}
