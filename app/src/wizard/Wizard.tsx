import { Captions, Cloud, Cpu, LoaderCircle, TriangleAlert, Zap } from "lucide-react";
import { useEffect, useReducer, useRef, useState } from "react";
import type { Backend } from "../api/client";
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
import { CPU_NOTICE, SelfTestPanel } from "../settings/HardwareSection";
import { chipOrGpu, isCpuProfile, isMac } from "../manage/hardwareText";
import { PROFILE_BLURB, PROFILE_NAME } from "../manage/profileText";
export const VC_REDIST_URL = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist";
import { downloadPlan } from "./plan";
import { initialWizard, reduceWizard } from "./flow";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function Wizard({ backend, onExit }: { backend: Backend; onExit: (how: "finished" | "skipped") => void }) {
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
          plan.items.filter((i) => i.fallback).map((i) => startAsset(backend, { id: i.id, type: i.type === "model" ? "model" : "runtime" })),
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
        (test) => (test ? dispatch({ type: "selfTested", test }) : dispatch({ type: "selfTestFailed", error: "自檢沒有回報結果" })),
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
            <span className="eyebrow">第一次使用</span>
            <h1>準備好翻譯需要的模型</h1>
          </div>
        </div>

        {state.step === "detect" && (
          <p className="note" data-testid="wizard-detecting">
            <LoaderCircle className="icon spin" aria-hidden />
            正在偵測這台電腦的硬體…
          </p>
        )}

        {state.step === "detect-failed" && (
          <>
            <p className="note bad" role="alert">
              {state.error}
            </p>
            <div className="dialog-buttons start">
              <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                略過
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
              {state.phase === "starting" && "正在開始下載…"}
              {state.phase === "running" && "下載中。可以隨時取消，之後會從中斷的地方續傳。"}
              {state.phase === "cancelled" && "已取消。已下載的部分會保留，按「繼續下載」會從中斷處續傳。"}
              {state.phase === "failed" && "下載沒有完成。"}
            </p>
            {state.jobs.length > 0 && <OverallLine jobs={state.jobs} />}
            {state.error && (
              <p className="note bad" role="alert" data-testid="wizard-error">
                {state.error}
              </p>
            )}
            <div className="dialog-buttons start">
              {state.phase === "running" && (
                <button type="button" data-testid="wizard-cancel" onClick={cancel}>
                  取消下載
                </button>
              )}
              {(state.phase === "cancelled" || state.phase === "failed") && (
                <>
                  <button type="button" className="primary" data-testid="wizard-retry" onClick={() => dispatch({ type: "retry" })}>
                    {state.phase === "cancelled" ? "繼續下載" : "重試"}
                  </button>
                  <button type="button" className="ghost" data-testid="wizard-back" onClick={() => dispatch({ type: "back" })}>
                    返回
                  </button>
                </>
              )}
              <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                略過
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
            <p>下載完成。正在實際啟動語音辨識與 LLM 做自檢，約 5 秒。</p>
            <SelfTestPanel result={null} running />
          </div>
        )}

        {state.step === "result" && (
          <div data-testid="wizard-result">
            {state.test && <SelfTestPanel result={state.test} running={false} />}
            {state.error && (
              <p className="note bad" role="alert" data-testid="wizard-error">
                {state.error}
              </p>
            )}
            <div className="dialog-buttons start">
              {state.test?.ok && (
                <button type="button" className="primary" data-testid="wizard-finish" onClick={() => dispatch({ type: "finish" })}>
                  開始使用
                </button>
              )}
              <button type="button" data-testid="wizard-rerun" onClick={() => dispatch({ type: "rerunSelfTest" })}>
                重新自檢
              </button>
              <button type="button" className="ghost" data-testid="wizard-back" onClick={() => dispatch({ type: "back" })}>
                換設定檔
              </button>
              {!state.test?.ok && (
                <button type="button" className="ghost" data-testid="wizard-skip" onClick={() => dispatch({ type: "skip" })}>
                  先略過
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function OverallLine({ jobs }: { jobs: readonly DownloadJob[] }) {
  const o = overall(jobs);
  const percent = Math.round(o.fraction * 100);
  return (
    <div className="overall" data-testid="wizard-overall">
      <div className="mbar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="sub">
        總進度 {percent}%（{bytes(o.done)} / {bytes(o.total)}）{o.speedBps > 0 ? ` · ${speed(o.speedBps)}` : ""}
      </p>
    </div>
  );
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
  const { view, selected } = state;
  const hw = view.hardware;
  const plan = downloadPlan(view, selected);
  const option = view.profiles.find((p) => p.id === selected);
  const others = view.profiles.length - 1;
  const tight = hw.diskFreeMib !== null && plan.totalBytes > hw.diskFreeMib * 1024 * 1024;
  return (
    <div data-testid="wizard-choose">
      <div className="detected" data-testid="wizard-hardware">
        <span>
          <strong data-testid="wizard-gpu">{chipOrGpu(hw).value}</strong>
          {!isMac(hw) && hw.vramMib !== null && <> · 顯示記憶體 {mib(hw.vramMib)}</>}
          {!isMac(hw) && hw.driverVersion && <> · 驅動 {hw.driverVersion}</>}
        </span>
        <span className="sub">
          {isMac(hw) ? "統一記憶體" : "記憶體"} {mib(hw.ramMib)} · 磁碟可用 {mib(hw.diskFreeMib)}
        </span>
      </div>
      {view.vcRuntimeMissing && (
        <div className="note bad" role="alert" data-testid="wizard-vcredist">
          這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64），語音辨識和翻譯程式無法啟動。請先
          <ExternalLink href={VC_REDIST_URL}>到 Microsoft 下載並安裝 vc_redist.x64.exe</ExternalLink>，裝好後再按「下載並開始」。
        </div>
      )}
      <p data-testid="wizard-recommended">
        建議使用 <strong>{PROFILE_NAME[view.recommended.id]}</strong> 設定檔。你也可以改選下面另外{others === 2 ? "兩" : others}個。
      </p>
      <div className="wizard-profiles" role="radiogroup" aria-label="設定檔">
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
              <strong>{PROFILE_NAME[p.id]}</strong>
              {p.recommended && <span className="chip-tag rec">建議</span>}
            </span>
            <span className="sub">{PROFILE_BLURB[p.id]}</span>
            {!p.fitsHardware && <span className="sub warn-text">這台電腦可能不夠用</span>}
          </button>
        ))}
      </div>

      {option?.recommendCloud && (
        <p className="note cloud" data-testid="wizard-cpu-note">
          <Cloud className="icon" aria-hidden />
          {CPU_NOTICE}
        </p>
      )}

      <h3>會下載的項目</h3>
      {plan.items.length === 0 ? (
        <p className="sub" data-testid="wizard-assets-empty">
          這個設定檔需要的項目都已安裝，直接做自檢。
        </p>
      ) : (
        <table className="inv wizard-assets" data-testid="wizard-assets">
          <thead>
            <tr>
              <th>項目</th>
              <th>大小</th>
              <th>授權</th>
            </tr>
          </thead>
          <tbody>
            {plan.items.map((item) => {
              const lic = licenses.get(item.id);
              return (
                <tr key={item.id} data-testid={`wizard-asset-${item.id}`}>
                  <td>
                    <span className="asset-id">{item.id}</span>
                    <span className="sub">
                      {item.type === "model" ? "模型" : "執行檔"}
                      {item.fallback ? "，GPU 失敗時改用 CPU 的備援" : ""}
                    </span>
                  </td>
                  <td>{bytes(item.sizeBytes)}</td>
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
        共 {bytes(plan.totalBytes)}
        {hw.diskFreeMib !== null && `，磁碟可用 ${mib(hw.diskFreeMib)}`}
      </p>
      {tight && (
        <p className="note bad" role="alert" data-testid="wizard-disk-warning">
          <TriangleAlert className="icon" aria-hidden />
          磁碟空間可能不夠，下載可能會失敗。
        </p>
      )}

      <div className="dialog-buttons start sticky-actions">
        <button type="button" className="primary" data-testid="wizard-start" onClick={onStart}>
          {plan.items.length === 0 ? "開始自檢" : "下載並開始"}
        </button>
        <button type="button" className="ghost" data-testid="wizard-skip" onClick={onSkip}>
          略過，之後在設定裡處理
        </button>
      </div>
    </div>
  );
}
