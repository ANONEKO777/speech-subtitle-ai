import { convertFileSrc } from "@tauri-apps/api/core";
import { type CSSProperties, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { openFolder, pickFolder } from "../api/backend";
import type { Backend, LanguageInfo } from "../api/client";
import { type Look, type Playback, takeStill } from "../api/library";
import { type Loaded, useCueEditing } from "../editor/useCueEditing";
import { exportItems, shortName } from "../export/exports";
import type { Settings } from "../settings/settings";
import { useSummary } from "../summary/useSummary";
import { Controls } from "./Controls";
import { BurnCard, HelpOverlay, Toast } from "./Overlays";
import { SidePanel, type Tab } from "./SidePanel";
import type { Cue } from "./cues";
import { type Action, isArrow, keyAction } from "./shortcuts";
import { adjacentCue, clampOffset, playClock, startOnVideo } from "./transport";
import { useActiveCue } from "./useActiveCue";
import { useBurn } from "./useBurn";
import { useOffset } from "./useOffset";
import { useToast } from "./useToast";
import { useTransport } from "./useTransport";

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly videoPath: string;
  readonly settings: Settings;
  readonly onSettings: (patch: Partial<Settings>) => void;
  readonly languages: readonly LanguageInfo[];
  readonly lang: string;
  readonly onLang: (code: string) => void;
  readonly loaded: Loaded;
  /** What the last run did with the person's edits, shown until something else happens. */
  readonly notice: string | null;
  /** Where the project was left and its subtitle offset. */
  readonly playback: Playback;
  readonly hasPrevVideo: boolean;
  readonly hasNextVideo: boolean;
  /** Plays the previous (-1) or next (1) video of the play queue. */
  readonly onStep: (dir: 1 | -1) => void;
  /** The library tab of the side column. */
  readonly library: ReactNode;
  /** The queue tab of the side column, and the text on its tab. */
  readonly batch: ReactNode;
  readonly batchBadge: string | null;
  /** Counts up each time something outside asks to show the queue tab. */
  readonly batchRequest: number;
}

function extension(path: string): string {
  return path.slice(path.lastIndexOf(".") + 1).toLowerCase();
}

/** A seek lands on the frame at or before the target. Aiming a few frames into the cue makes that frame belong to the cue, so its subtitle shows. */
const SEEK_NUDGE_MS = 50;
const CLIP_S = 30;
const IDLE_MS = 2500;

/** True when the key should go to the focused control, not the player. */
function ownsKey(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || /^(TEXTAREA|SELECT)$/.test(target.tagName)) return true;
  if (target instanceof HTMLInputElement) return target.type === "range" ? isArrow(key) : true;
  return false;
}

export function Player(props: Props) {
  const { backend, projectId, videoPath, settings, onSettings, languages, lang, onLang, loaded, notice, playback } = props;
  const video = useRef<HTMLVideoElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [unplayable, setUnplayable] = useState(false);
  const [tab, setTab] = useState<Tab>("cues");
  const seenBatchRequest = useRef(props.batchRequest);
  useEffect(() => {
    if (props.batchRequest !== seenBatchRequest.current) {
      seenBatchRequest.current = props.batchRequest;
      setTab("queue");
    }
  }, [props.batchRequest]);
  const [status, setStatus] = useState<string | null>(notice);
  const [helpOpen, setHelpOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [idle, setIdle] = useState(false);
  const [osd, setOsd] = useState<string | null>(null);
  const osdTimer = useRef(0);
  const idleTimer = useRef(0);
  const { toast, show: showToast, hide: hideToast } = useToast();

  const editing = useCueEditing(backend, projectId, lang, loaded);
  const summary = useSummary(backend, projectId, lang);
  const cues = editing.state.cues;
  const { offsetMs, change: changeOffset } = useOffset(backend, projectId, playback.offsetMs);
  const active = useActiveCue(video, cues, offsetMs);
  const cue = active >= 0 ? cues[active] : undefined;

  const say = useCallback((text: string | void) => {
    if (!text) return;
    window.clearTimeout(osdTimer.current);
    setOsd(text);
    osdTimer.current = window.setTimeout(() => setOsd(null), 1100);
  }, []);

  const t = useTransport(video, {
    backend,
    projectId,
    savedPosition: playback.positionS,
    onResumed: (at) =>
      showToast({ text: `已從 ${playClock(at)} 繼續`, action: { label: "從頭播放", run: () => video.current && (video.current.currentTime = 0) } }),
    onEnded: () => {
      if (props.hasNextVideo) props.onStep(1);
    },
  });

  useEffect(() => setStatus(notice), [notice]);
  useEffect(() => () => window.clearTimeout(osdTimer.current), []);

  const undo = editing.undo;
  const label = shortName(languages.find((l) => l.code === lang)?.nativeName ?? lang);

  const look = useCallback((): Look => {
    const v = video.current;
    const box = v?.clientHeight ?? 0;
    const picture = v && v.videoWidth > 0 ? Math.min(box, (v.clientWidth * v.videoHeight) / v.videoWidth) : box;
    return {
      mode: settings.mode,
      zhFirst: settings.zhFirst,
      sizeRatio: picture > 0 ? Math.min(0.2, Math.max(0.01, settings.fontSize / picture)) : 0.045,
      color: settings.color,
    };
  }, [settings.mode, settings.zhFirst, settings.fontSize, settings.color]);

  const fail = useCallback((what: string, e: unknown) => showToast({ text: `${what}：${e instanceof Error ? e.message : String(e)}`, error: true }), [showToast]);

  const shoot = useCallback(
    async (burn: boolean) => {
      const v = video.current;
      if (!v) return;
      try {
        const still = await takeStill(backend, projectId, { timeS: v.currentTime, lang, burn, dir: settings.outputDir, look: look() });
        const copied = await navigator.clipboard
          .write([new ClipboardItem({ "image/png": still.png })])
          .then(() => true)
          .catch(() => false);
        showToast({
          text: `截圖已存到 ${still.path}${copied ? "，已複製到剪貼簿" : "（無法複製到剪貼簿）"}`,
          action: { label: "開啟資料夾", run: () => void openFolder(still.path).catch((e: unknown) => fail("無法開啟資料夾", e)) },
        });
      } catch (e) {
        fail("截圖失敗", e);
      }
    },
    [backend, projectId, lang, settings.outputDir, look, showToast, fail],
  );

  const burn = useBurn(backend, (view) => {
    if (view.state === "done") {
      showToast({
        text: `已匯出燒入字幕的影片 ${view.output}`,
        action: { label: "開啟資料夾", run: () => void openFolder(view.output).catch((e: unknown) => fail("無法開啟資料夾", e)) },
      });
    } else if (view.state === "failed") fail("匯出失敗", view.error ?? "");
    else showToast({ text: "已取消匯出" });
  });
  const startBurn = (clip: boolean) =>
    void burn.start(projectId, {
      lang,
      dir: settings.outputDir,
      look: look(),
      startS: clip ? (video.current?.currentTime ?? 0) : 0,
      durationS: clip ? CLIP_S : null,
    });

  const seekMs = useCallback((ms: number) => {
    if (video.current) video.current.currentTime = ms / 1000;
  }, []);
  const seekCue = useCallback(
    (c: Cue) => seekMs(Math.min(startOnVideo(c, offsetMs) + SEEK_NUDGE_MS, c.endMs + offsetMs - 1)),
    [seekMs, offsetMs],
  );
  const seekChapter = useCallback(
    (seconds: number) => {
      seekMs(seconds * 1000);
      setTab("cues");
    },
    [seekMs],
  );

  const jumpLine = (dir: 1 | -1) => {
    const now = (video.current?.currentTime ?? 0) * 1000;
    const i = adjacentCue(cues, offsetMs, now, dir);
    const target = i === null ? undefined : cues[i];
    if (!target) return say(dir > 0 ? "沒有下一句" : "沒有上一句");
    seekCue(target);
    say(`第 ${(i ?? 0) + 1} 句`);
  };

  const nudgeOffset = (delta: number) => {
    const next = clampOffset(offsetMs + delta);
    changeOffset(next);
    say(`字幕 ${next >= 0 ? "+" : "−"}${(Math.abs(next) / 1000).toFixed(1)} 秒`);
  };

  const togglePip = async () => {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else {
        await video.current?.requestPictureInPicture();
        showToast({ text: "子母畫面只有影片，字幕仍在主視窗" });
      }
    } catch (e) {
      fail("無法開啟子母畫面", e);
    }
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stage.current?.requestFullscreen().catch((e: unknown) => fail("無法進入全螢幕", e));
  };

  const run = (a: Action) => {
    switch (a.kind) {
      case "toggle-play":
        return t.togglePlay();
      case "seek":
        return say(t.seekBy(a.seconds));
      case "seek-percent":
        return say(t.seekPercent(a.percent));
      case "volume":
        return say(t.volumeBy(a.delta));
      case "mute":
        return say(t.toggleMute());
      case "fullscreen":
        return toggleFullscreen();
      case "screenshot":
        return void shoot(settings.burnShots !== a.invertBurn);
      case "speed":
        return say(t.speedStep(a.dir));
      case "frame":
        return say(t.frameStep(a.dir));
      case "line":
        return jumpLine(a.dir);
      case "loop":
        return say(t.cycleLoop());
      case "pip":
        return void togglePip();
      case "offset":
        return nudgeOffset(a.deltaMs);
      case "video":
        return props.onStep(a.dir);
      case "help":
        return setHelpOpen((v) => !v);
    }
  };
  const latest = useRef(run);
  latest.current = run;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z" && !ownsKey(e.target, "z")) {
        e.preventDefault();
        void undo();
        return;
      }
      if (e.key === "Escape") {
        setHelpOpen(false);
        return;
      }
      if (e.repeat && !isArrow(e.key) && e.key !== "," && e.key !== ".") return;
      if (ownsKey(e.target, e.key)) return;
      const action = keyAction(e);
      if (!action) return;
      e.preventDefault();
      latest.current(action);
    };
    const swallowSpace = (e: KeyboardEvent) => {
      if (e.key === " " && !ownsKey(e.target, e.key)) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", swallowSpace);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", swallowSpace);
    };
  }, [undo]);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stage.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const wake = () => {
    setIdle(false);
    window.clearTimeout(idleTimer.current);
    idleTimer.current = window.setTimeout(() => setIdle(true), IDLE_MS);
  };
  useEffect(() => () => window.clearTimeout(idleTimer.current), []);

  const lines: Array<{ lang: "en" | "zh"; text: string }> = [];
  if (cue && settings.mode !== "zh") lines.push({ lang: "en", text: cue.en });
  if (cue && settings.mode !== "en") lines.push({ lang: "zh", text: cue.zh });
  if (settings.zhFirst) lines.reverse();

  const subtitleStyle = {
    "--sub-size": `${settings.fontSize}px`,
    "--sub-lh": settings.lineHeight,
    color: settings.color,
  } as CSSProperties;

  return (
    <div className="player">
      <div
        className="stage"
        ref={stage}
        data-testid="stage"
        data-fullscreen={fullscreen}
        data-overlay={settings.fsOverlay}
        data-idle={idle && !t.paused}
        onMouseMove={wake}
      >
        <div className="video-wrap">
          <video
            key={videoPath}
            ref={video}
            data-testid="video"
            src={convertFileSrc(videoPath)}
            onError={() => setUnplayable(true)}
            onClick={() => t.togglePlay()}
            onDoubleClick={toggleFullscreen}
            {...t.videoProps}
          />
          {osd && (
            <div className="osd" data-testid="osd" aria-live="polite">
              {osd}
            </div>
          )}
          <BurnCard view={burn.view} error={burn.error} onCancel={burn.cancel} />
          <Toast toast={toast} onClose={hideToast} />
          <Controls
            paused={t.paused}
            time={t.time}
            duration={t.duration}
            volume={t.volume}
            muted={t.muted}
            rate={t.rate}
            loop={t.loop}
            offsetMs={offsetMs}
            fullscreen={fullscreen}
            hasPrevVideo={props.hasPrevVideo}
            hasNextVideo={props.hasNextVideo}
            burnShots={settings.burnShots}
            fsOverlay={settings.fsOverlay}
            outputDir={settings.outputDir}
            onPlay={t.togglePlay}
            onSeek={t.seekTo}
            onVolume={t.setVolumeTo}
            onMute={() => say(t.toggleMute())}
            onRate={(r) => say(t.setRateTo(r))}
            onLoop={() => say(t.cycleLoop())}
            onLine={jumpLine}
            onVideo={props.onStep}
            onOffset={(ms) => changeOffset(ms)}
            onShot={() => void shoot(settings.burnShots)}
            onPip={() => void togglePip()}
            onFullscreen={toggleFullscreen}
            onBurnShots={(burnShots) => onSettings({ burnShots })}
            onFsOverlay={(fsOverlay) => onSettings({ fsOverlay })}
            onPickFolder={() =>
              void pickFolder().then(
                (dir) => dir && onSettings({ outputDir: dir }),
                (e: unknown) => fail("無法選擇資料夾", e),
              )
            }
            onHelp={() => setHelpOpen(true)}
          />
          {helpOpen && <HelpOverlay onClose={() => setHelpOpen(false)} />}
        </div>
        {unplayable && (
          <div className="notice" role="alert" data-testid="unplayable">
            這個 {extension(videoPath).toUpperCase()} 檔無法在內建播放器播放。請先轉成 H.264/AAC 的 MP4（proxy）再匯入。字幕仍可在右側清單查看。
          </div>
        )}
        <div className="subtitle" data-testid="subtitle" style={subtitleStyle}>
          {lines.map((line) => (
            <p key={line.lang} data-lang={line.lang}>
              {line.text}
            </p>
          ))}
        </div>
      </div>
      <SidePanel
        backend={backend}
        projectId={projectId}
        tab={tab}
        onTab={setTab}
        editing={editing}
        active={active}
        mode={settings.mode}
        languages={languages}
        lang={lang}
        onLang={onLang}
        summary={summary?.text}
        summaryDegraded={summary?.degraded ?? false}
        exports={exportItems(videoPath, lang, label)}
        actions={[
          { id: "burn-full", label: "MP4 燒入字幕（整部）", run: () => startBurn(false), disabled: burn.view?.state === "running" },
          { id: "burn-clip", label: `MP4 燒入字幕（從目前位置 ${CLIP_S} 秒）`, run: () => startBurn(true), disabled: burn.view?.state === "running" },
        ]}
        status={status}
        onStatus={setStatus}
        onSeekCue={seekCue}
        onSeekSeconds={seekChapter}
        library={props.library}
        batch={props.batch}
        batchBadge={props.batchBadge}
      />
    </div>
  );
}
