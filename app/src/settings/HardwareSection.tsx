import { CircleCheck, Cloud, Cpu, LoaderCircle, MemoryStick, TriangleAlert, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { Backend } from "../api/client";
import { cancelDownload, chooseProfile, downloadProfileAssets, fetchLastSelfTest, fetchProfile, runSelfTest } from "../manage/api";
import { isActive, overall } from "../manage/downloads";
import { bytes, mib } from "../manage/format";
import { chipOrGpu, deviceLabel, isCpuProfile, isMac } from "../manage/hardwareText";
import { JobRow } from "../manage/JobRow";
import { LOCAL_BUILD_TEXT, toBuild, toDownload } from "../manage/localBuild";
import { PROFILE_BLURB, PROFILE_NAME } from "../manage/profileText";
import type { Downloads } from "../manage/useDownloads";
import type { ProfileId, ProfileOption, ProfileView, SelfTest } from "../manage/types";

export const CPU_NOTICE =
  "CPU 設定檔沒有 GPU 加速，本機內建的 LLM 會慢很多。建議改用雲端 LLM：翻譯快、品質好，差別是影片的逐字稿與字幕內容會傳送到雲端服務，離開這台電腦。內建與 Ollama 全程在本機，不會外傳。";


export function selfTestText(t: SelfTest): { tone: "ok" | "warn" | "bad"; title: string; body: string } {
  if (t.ok && t.fallback) return { tone: "warn", title: "GPU 後端失敗，已改用 CPU", body: t.fallback.reason };
  if (t.ok) return { tone: "ok", title: `自檢通過，使用 ${deviceLabel(t.device)}`, body: `${t.seconds.toFixed(1)} 秒` };
  return { tone: "bad", title: "自檢沒有通過", body: t.message };
}

export function SelfTestPanel({ result, running }: { result: SelfTest | null; running: boolean }) {
  if (running) {
    return (
      <p className="note" data-testid="selftest-running">
        <LoaderCircle className="icon spin" aria-hidden />
        自檢中，約需 5 到 10 秒…
      </p>
    );
  }
  if (!result) return null;
  const text = selfTestText(result);
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
                {s.stage === "asr" ? "語音辨識" : "LLM"} · {s.runtimeId} · {s.device} · {s.ok ? "正常" : "失敗"}（{s.seconds.toFixed(1)} 秒）
                {s.ok ? "" : `：${s.detail}`}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function missingText(option: ProfileOption): string {
  if (option.missing.length === 0) return "需要的項目都已安裝";
  const get = toDownload(option.missing);
  const build = toBuild(option.missing);
  const download = `缺少 ${get.length} 項，要下載 ${bytes(option.downloadBytes)}`;
  if (build.length === 0) return download;
  const built = `${build.length} 項要${LOCAL_BUILD_TEXT}`;
  return get.length === 0 ? built : `${download}；另有 ${built}`;
}

interface Props {
  readonly backend: Backend;
  readonly downloads: Downloads;
  readonly onOpenLlm: () => void;
}

export function HardwareSection({ backend, downloads, onOpenLlm }: Props) {
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
  const first = hw ? chipOrGpu(hw) : null;
  return (
    <section className="panel" data-testid="hardware-section" aria-labelledby="hw-title">
      <div className="panel-head">
        <div>
          <h2 id="hw-title">硬體與效能</h2>
          <p className="muted">App 偵測這台電腦的硬體並建議設定檔。你隨時可以改選，不必重裝。</p>
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
            <h3>偵測到的硬體</h3>
            <dl className="facts">
              <div>
                <dt>{first?.label}</dt>
                <dd data-testid="hw-gpu">{first?.value}</dd>
              </div>
              {!isMac(hw) && (
                <>
                  <div>
                    <dt>顯示記憶體</dt>
                    <dd data-testid="hw-vram">{mib(hw.vramMib)}</dd>
                  </div>
                  <div>
                    <dt>驅動程式</dt>
                    <dd data-testid="hw-driver">{hw.driverVersion ?? "—"}</dd>
                  </div>
                </>
              )}
              <div>
                <dt>{isMac(hw) ? "統一記憶體" : "記憶體"}</dt>
                <dd data-testid="hw-ram">{mib(hw.ramMib)}</dd>
              </div>
              <div>
                <dt>磁碟可用空間</dt>
                <dd data-testid="hw-disk">{mib(hw.diskFreeMib)}</dd>
              </div>
            </dl>
            <p data-testid="hw-recommended">
              建議的設定檔：<strong>{PROFILE_NAME[view.recommended.id]}</strong>
            </p>
            <details>
              <summary>為什麼這樣建議</summary>
              <pre className="why">{view.recommended.why}</pre>
            </details>
          </div>

          <div className="profiles" role="radiogroup" aria-label="設定檔" data-testid="profiles">
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
                  <strong>{PROFILE_NAME[p.id]}</strong>
                </div>
                <p className="sub">{PROFILE_BLURB[p.id]}</p>
                <div className="chips">
                  {p.active && <span className="chip-tag on">目前使用</span>}
                  {p.recommended && <span className="chip-tag rec">建議</span>}
                  {!p.fitsHardware && <span className="chip-tag warn">這台電腦可能不夠</span>}
                </div>
                <p className="sub" data-testid={`profile-${p.id}-missing`}>
                  {missingText(p)}
                </p>
                {p.recommendCloud && (
                  <p className="note cloud" data-testid="cpu-cloud-note">
                    <Cloud className="icon" aria-hidden />
                    {CPU_NOTICE}
                  </p>
                )}
                <button type="button" className={p.active ? "ghost" : "primary"} data-testid={`profile-use-${p.id}`} disabled={p.active || busy} onClick={() => void choose(p.id)}>
                  {p.active ? "使用中" : "使用這個設定檔"}
                </button>
              </div>
            ))}
          </div>

          {view.active.source === "user" && (
            <button type="button" className="ghost link" data-testid="profile-auto" disabled={busy} onClick={() => void choose(null)}>
              改回自動：依硬體使用建議的設定檔
            </button>
          )}
          {active?.recommendCloud && (
            <button type="button" className="ghost link" data-testid="goto-llm" onClick={onOpenLlm}>
              前往設定 LLM 來源（雲端）
            </button>
          )}

          {switched && (
            <div className="callout" data-testid="switch-result" data-profile={switched.id}>
              <MemoryStick className="icon" aria-hidden />
              <div>
                <p>
                  已切換到 <strong>{PROFILE_NAME[switched.id]}</strong>。
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
                        ? `還缺 ${toDownload(active.missing).length} 項，共 ${bytes(active.downloadBytes)}：`
                        : "還缺的項目要在這台 Mac 上自行建置："}
                    </p>
                    <ul className="stages" data-testid="switch-missing">
                      {active.missing.map((m) => (
                        <li key={m.id}>
                          {m.id}（{m.type === "model" ? "模型" : "執行檔"}，{m.localBuild ? LOCAL_BUILD_TEXT : bytes(m.sizeBytes)}）
                        </li>
                      ))}
                    </ul>
                    {jobs.length === 0 && toDownload(active.missing).length > 0 && (
                      <button type="button" className="primary" data-testid="switch-download" onClick={() => void fetchMissing()}>
                        下載缺少的項目
                      </button>
                    )}
                  </>
                ) : (
                  <p data-testid="switch-complete">這個設定檔需要的項目都已安裝。</p>
                )}
                {jobs.length > 0 && (
                  <div className="jobs" data-testid="switch-jobs">
                    {jobs.map((j) => (
                      <JobRow key={j.id} job={j} testId={`switch-job-${j.assetId}`} />
                    ))}
                    {jobs.some(isActive) && (
                      <p className="sub" data-testid="switch-overall">
                        總進度 {Math.round(total.fraction * 100)}%
                        <button type="button" className="ghost" onClick={() => jobs.filter(isActive).forEach((j) => void cancelDownload(backend, j.id))}>
                          全部取消
                        </button>
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="card manage-card">
            <h3>自檢</h3>
            <p className="muted">用目前的設定檔實際啟動語音辨識與 LLM。GPU 失敗時會自動改用 CPU，並寫出原因。</p>
            {view.fallback && !test && (
              <p className="note warn" data-testid="fallback-banner">
                目前使用 CPU：{view.fallback.reason}
              </p>
            )}
            <button type="button" data-testid="selftest-run" disabled={testing} onClick={() => void selfTest()}>
              {testing ? "自檢中…" : "執行自檢"}
            </button>
            <SelfTestPanel result={test} running={testing} />
          </div>
        </>
      )}
    </section>
  );
}
