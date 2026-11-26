import { Captions, Cloud, Cpu, LoaderCircle, TriangleAlert, Zap } from "lucide-react";
import { useEffect, useReducer, useRef, useState } from "react";
import type { Backend } from "../api/client";
import type { Translate } from "../i18n";
import type { Locale } from "../i18n/locale";
import { useT } from "../i18n/I18nProvider";
import {
  cancelDownload,
  chooseProfile,
  downloadProfileAssets,
  fetchLicenses,
  fetchProfile,
  runSelfTest,
  startAsset,
} from "../manage/api";
import { isActive, overall } from "../manage/downloads";
import { ExternalLink } from "../manage/ExternalLink";
import { bytes, mib, speed } from "../manage/format";
import { JobRow } from "../manage/JobRow";
import type { DownloadJob, LicenseEntry, ProfileId } from "../manage/types";
import { useDownloads } from "../manage/useDownloads";
import { SelfTestPanel, cpuNotice } from "../settings/HardwareSection";
import { chipOrGpu, isCpuProfile, isMac } from "../manage/hardwareText";
import { localBuildText, toBuild, toDownload } from "../manage/localBuild";
import { profileBlurb, profileName } from "../manage/profileText";
export const VC_REDIST_URL = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist";
import { downloadPlan } from "./plan";
import { type WizardError, initialWizard, reduceWizard } from "./flow";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function Wizard({ backend, onExit }: { backend: Backend; onExit: (how: "finished" | "skipped") => void }) {
  const { t } = useT();
  const [state, dispatch] = useReducer(reduceWizard, initialWizard);
  const [licenses, setLicenses] = useState<ReadonlyMap<string, LicenseEntry>>(new Map());
  const downloads = useDownloads(backend);
  const testing = useRef(false);

  useEffect(() => {
    fetchProfile(backend).then(
      (view) => dispatch({ type: "loaded", view }),
      (e: unknown) => dispatch({ type: "loadFailed", error: message(e) }),
    );
    void fetchLicenses(backend).then((list) => setLicenses(new Map(list.map((l) => [l.id, l]))), () => undefined);
  }, [backend]);

  useEffect(() => {
    if (state.step === "finished" || state.step === "skipped") onExit(state.step);
  }, [state.step, onExit]);

  const starting = state.step === "download" && state.phase === "starting";
  useEffect(() => {
    if (state.step !== "download" || state.phase !== "starting") return;
    const { view, selected } = state;
    let alive = true;
    void (async () => {
      try {
        await chooseProfile(backend, selected === view.recommended.id ? null : selected);
        const jobs = await downloadProfileAssets(backend);
        const plan = downloadPlan(view, selected);
        const extra = await Promise.all(
          plan.items.filter((i) => i.fallback && !i.localBuild).map((i) => startAsset(backend, { id: i.id, type: i.type === "model" ? "model" : "runtime" })),
        );
        if (!alive) return;
        downloads.refresh();
        dispatch({ type: "started", jobIds: [...jobs, ...extra].map((j) => j.id) });
      } catch (e) {
        if (alive) dispatch({ type: "startFailed", error: message(e) });
      }
    })();
    return () => {
      alive = false;
    };
  }, [starting, backend]);

  const running = state.step === "download" && state.phase === "running";
  useEffect(() => {
    if (running) dispatch({ type: "polled", jobs: downloads.list });
  }, [downloads.list, running]);

  const selfTesting = state.step === "selftest";
  useEffect(() => {
    if (!selfTesting || testing.current) return;
    testing.current = true;
    runSelfTest(backend)
      .then(
        (test) => (test ? dispatch({ type: "selfTested", test }) : dispatch({ type: "selfTestFailed", error: null })),
        (e: unknown) => dispatch({ type: "selfTestFailed", error: message(e) }),
      )
      .finally(() => {
        testing.current = false;
      });
  }, [selfTesting, backend]);

  const cancel = () => {
    if (state.step !== "download") return;
    for (const job of state.jobs.filter(isActive)) void cancelDownload(backend, job.id);
    dispatch({ type: "cancelDownload" });
  };

  return (
    <section className="wizard" data-testid="wizard" data-step={state.step}>
      <div className="card wizard-card">
        <div className="wizard-head">
          <span className="badge-icon">
            <Captions aria-hidden />
          </span>
          <div>
            <span className="eyebrow">{t("wizard.eyebrow")}</span>
            <h1>{t("wizard.title")}</h1>
          </div>
        </div>

        {state.step === "detect" && (
          <p className="note" data-testid="wizard-detecting">
            <LoaderCircle className="icon spin" aria-hidden />
            {t("wizard.detecting")}
          </p>
        )}

        {state.step === "detect-failed" && (
          <>
            <p className="note bad" role="alert">
              {state.error}
            </p>
            <div className="dialog-buttons start">
              <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                {t("wizard.skip")}
              </button>
            </div>
          </>
        )}

        {state.step === "choose" && (
          <Choose
            state={state}
            licenses={licenses}
            onSelect={(profile) => dispatch({ type: "select", profile })}
            onStart={() => dispatch({ type: "start" })}
            onSkip={() => dispatch({ type: "skip" })}
          />
        )}

        {state.step === "download" && (
          <div data-testid="wizard-download" data-phase={state.phase}>
            <p>
              {state.phase === "starting" && t("wizard.starting")}
              {state.phase === "running" && t("wizard.running")}
              {state.phase === "cancelled" && t("wizard.cancelled", { resume: t("wizard.resume") })}
              {state.phase === "failed" && t("wizard.failed")}
            </p>
            {state.jobs.length > 0 && <OverallLine jobs={state.jobs} />}
            {state.error && (
              <p className="note bad" role="alert" data-testid="wizard-error">
                {errorText(state.error, t)}
              </p>
            )}
            <div className="dialog-buttons start">
              {state.phase === "running" && (
                <button type="button" data-testid="wizard-cancel" onClick={cancel}>
                  {t("wizard.cancel")}
                </button>
              )}
              {(state.phase === "cancelled" || state.phase === "failed") && (
                <>
                  <button type="button" className="primary" data-testid="wizard-retry" onClick={() => dispatch({ type: "retry" })}>
                    {state.phase === "cancelled" ? t("wizard.resume") : t("wizard.retry")}
                  </button>
                  <button type="button" className="ghost" data-testid="wizard-back" onClick={() => dispatch({ type: "back" })}>
                    {t("wizard.back")}
                  </button>
                </>
              )}
              <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                {t("wizard.skip")}
              </button>
            </div>
            {state.jobs.length > 0 && (
              <div className="jobs scroll" data-testid="wizard-jobs">
                {state.jobs.map((j) => (
                  <JobRow key={j.id} job={j} testId={`wizard-job-${j.assetId}`} />
                ))}
              </div>
            )}
          </div>
        )}

        {state.step === "selftest" && (
          <div data-testid="wizard-selftest">
            <p>{t("wizard.selftest")}</p>
            <SelfTestPanel result={null} running />
          </div>
        )}

        {state.step === "result" && (
          <div data-testid="wizard-result">
            {state.test && <SelfTestPanel result={state.test} running={false} />}
            {(state.error || state.test === null) && (
              <p className="note bad" role="alert" data-testid="wizard-error">
                {state.error || t("wizard.noResult")}
              </p>
            )}
            <div className="dialog-buttons start">
              {state.test?.ok && (
                <button type="button" className="primary" data-testid="wizard-finish" onClick={() => dispatch({ type: "finish" })}>
                  {t("wizard.finish")}
                </button>
              )}
              <button type="button" data-testid="wizard-rerun" onClick={() => dispatch({ type: "rerunSelfTest" })}>
                {t("wizard.rerun")}
              </button>
              <button type="button" className="ghost" data-testid="wizard-back" onClick={() => dispatch({ type: "back" })}>
                {t("wizard.changeProfile")}
              </button>
              {!state.test?.ok && (
                <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                  {t("wizard.skipForNow")}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

const errorText = (error: WizardError, t: Translate): string =>
  typeof error === "string" ? error : t("wizard.jobFailed", { id: error.assetId, message: error.message ?? t("wizard.downloadFailed") });

function OverallLine({ jobs }: { jobs: readonly DownloadJob[] }) {
  const { t, locale } = useT();
  const o = overall(jobs);
  const percent = Math.round(o.fraction * 100);
  const line = t("wizard.overall", { percent, done: bytes(o.done, locale), total: bytes(o.total, locale) });
  return (
    <div className="overall" data-testid="wizard-overall">
      <div className="mbar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="sub">{o.speedBps > 0 ? t("wizard.overall.speed", { overall: line, speed: speed(o.speedBps, locale) }) : line}</p>
    </div>
  );
}

/** A count of other profiles as a word for two and three, a digit for more. */
const othersText = (n: number, t: Translate): string => (n === 2 ? t("wizard.others.two") : n === 3 ? t("wizard.others.three") : String(n));

/** The table lists what to download and, on a Mac, the runtime the build script makes. The heading says which of the two it holds. */
const assetsTitle = (downloads: number, builds: number, t: Translate): string =>
  builds === 0 ? t("wizard.assets.download") : downloads === 0 ? t("wizard.assets.build") : t("wizard.assets.both");

function totalText(nothingToDownload: boolean, totalBytes: number, disk: string | null, locale: Locale, t: Translate): string {
  if (nothingToDownload) return disk === null ? t("wizard.total.none") : t("wizard.total.noneDisk", { disk });
  const size = bytes(totalBytes, locale);
  return disk === null ? t("wizard.total.size", { size }) : t("wizard.total.sizeDisk", { size, disk });
}

function Choose({
  state,
  licenses,
  onSelect,
  onStart,
  onSkip,
}: {
  state: Extract<ReturnType<typeof reduceWizard>, { step: "choose" }>;
  licenses: ReadonlyMap<string, LicenseEntry>;
  onSelect: (p: ProfileId) => void;
  onStart: () => void;
  onSkip: () => void;
}) {
  const { t, locale } = useT();
  const { view, selected } = state;
  const hw = view.hardware;
  const plan = downloadPlan(view, selected);
  const option = view.profiles.find((p) => p.id === selected);
  const others = view.profiles.length - 1;
  const downloads = toDownload(plan.items);
  const builds = toBuild(plan.items);
  const tight = hw.diskFreeMib !== null && plan.totalBytes > hw.diskFreeMib * 1024 * 1024;
  const disk = mib(hw.diskFreeMib, locale);
  return (
    <div data-testid="wizard-choose">
      <div className="detected" data-testid="wizard-hardware">
        <span>
          <strong data-testid="wizard-gpu">{chipOrGpu(hw, t).value}</strong>
          {!isMac(hw) && hw.vramMib !== null && <> · {t("wizard.hw.vram", { size: mib(hw.vramMib, locale) })}</>}
          {!isMac(hw) && hw.driverVersion && <> · {t("wizard.hw.driver", { version: hw.driverVersion })}</>}
        </span>
        <span className="sub">
          {isMac(hw) ? t("wizard.hw.unified", { size: mib(hw.ramMib, locale) }) : t("wizard.hw.ram", { size: mib(hw.ramMib, locale) })} ·{" "}
          {t("wizard.hw.disk", { size: disk })}
        </span>
      </div>
      {view.vcRuntimeMissing && (
        <div className="note bad vc-note" role="alert" data-testid="wizard-vcredist">
          {t("wizard.vc.pre")}
          <ExternalLink href={VC_REDIST_URL}>{t("wizard.vc.link")}</ExternalLink>
          {t("wizard.vc.post", { start: t("wizard.start.download") })}
        </div>
      )}
      <p data-testid="wizard-recommended">
        {t("wizard.recommended.pre")}
        <strong>{profileName(view.recommended.id, t)}</strong>
        {t("wizard.recommended.post", { others: othersText(others, t) })}
      </p>
      <div className="wizard-profiles" role="radiogroup" aria-label={t("wizard.profiles")}>
        {view.profiles.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={p.id === selected}
            className="source-choice"
            data-testid={`wizard-profile-${p.id}`}
            data-recommended={p.recommended}
            onClick={() => onSelect(p.id)}
          >
            <span className="profile-title">
              {isCpuProfile(p.id) ? <Cpu className="icon" aria-hidden /> : <Zap className="icon" aria-hidden />}
              <strong>{profileName(p.id, t)}</strong>
              {p.recommended && <span className="chip-tag rec">{t("wizard.recommendedTag")}</span>}
            </span>
            <span className="sub">{profileBlurb(p.id, t)}</span>
            {!p.fitsHardware && <span className="sub warn-text">{t("wizard.mayNotFit")}</span>}
          </button>
        ))}
      </div>

      {option?.recommendCloud && (
        <p className="note cloud" data-testid="wizard-cpu-note">
          <Cloud className="icon" aria-hidden />
          {cpuNotice(option.id, t)}
        </p>
      )}

      <h3 data-testid="wizard-assets-title">{assetsTitle(downloads.length, builds.length, t)}</h3>
      {plan.items.length === 0 ? (
        <p className="sub" data-testid="wizard-assets-empty">
          {t("wizard.assets.none")}
        </p>
      ) : (
        <table className="inv wizard-assets" data-testid="wizard-assets">
          <thead>
            <tr>
              <th>{t("wizard.col.item")}</th>
              <th>{t("wizard.col.size")}</th>
              <th>{t("wizard.col.license")}</th>
            </tr>
          </thead>
          <tbody>
            {plan.items.map((item) => {
              const lic = licenses.get(item.id);
              const notes = [
                item.type === "model" ? t("asset.model") : t("asset.program"),
                ...(item.localBuild ? [localBuildText(t)] : []),
                ...(item.fallback ? [t("wizard.item.fallback")] : []),
              ];
              return (
                <tr key={item.id} data-testid={`wizard-asset-${item.id}`}>
                  <td>
                    <span className="asset-id">{item.id}</span>
                    <span className="sub">{notes.join(t("wizard.item.sep"))}</span>
                  </td>
                  <td>{item.localBuild ? "—" : bytes(item.sizeBytes, locale)}</td>
                  <td>
                    {lic ? (
                      <ExternalLink href={lic.licenseUrl} testId={`wizard-license-${item.id}`}>
                        {lic.license}
                      </ExternalLink>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="sub" data-testid="wizard-total">
        {totalText(downloads.length === 0 && builds.length > 0, plan.totalBytes, hw.diskFreeMib !== null ? disk : null, locale, t)}
      </p>
      {tight && (
        <p className="note bad" role="alert" data-testid="wizard-disk-warning">
          <TriangleAlert className="icon" aria-hidden />
          {t("wizard.diskWarning")}
        </p>
      )}

      <div className="dialog-buttons start sticky-actions">
        <button type="button" className="primary" data-testid="wizard-start" onClick={onStart}>
          {downloads.length === 0 ? t("wizard.start.selftest") : t("wizard.start.download")}
        </button>
        <button type="button" className="ghost" data-testid="wizard-skip" onClick={onSkip}>
          {t("wizard.skipLater")}
        </button>
      </div>
    </div>
  );
}
