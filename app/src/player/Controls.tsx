import {
  Camera,
  Captions,
  ChevronLeft,
  ChevronRight,
  Ellipsis,
  FolderOpen,
  Gauge,
  Maximize,
  Minimize,
  Pause,
  PictureInPicture2,
  Play,
  Repeat,
  SkipBack,
  SkipForward,
  Volume1,
  Volume2,
  VolumeX,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { useT } from "../i18n/I18nProvider";
import { type Loop, SPEEDS, formatOffset, playClock } from "./transport";

type Open = "speed" | "offset" | "more" | null;

export interface ControlsProps {
  readonly paused: boolean;
  readonly time: number;
  readonly duration: number;
  readonly volume: number;
  readonly muted: boolean;
  readonly rate: number;
  readonly loop: Loop;
  readonly offsetMs: number;
  readonly fullscreen: boolean;
  readonly hasPrevVideo: boolean;
  readonly hasNextVideo: boolean;
  readonly burnShots: boolean;
  readonly fsOverlay: boolean;
  readonly outputDir: string;
  readonly onPlay: () => void;
  readonly onSeek: (seconds: number) => void;
  readonly onVolume: (volume: number) => void;
  readonly onMute: () => void;
  readonly onRate: (rate: number) => void;
  readonly onLoop: () => void;
  readonly onLine: (dir: 1 | -1) => void;
  readonly onVideo: (dir: 1 | -1) => void;
  readonly onOffset: (ms: number) => void;
  readonly onShot: () => void;
  readonly onPip: () => void;
  readonly onFullscreen: () => void;
  readonly onBurnShots: (on: boolean) => void;
  readonly onFsOverlay: (on: boolean) => void;
  readonly onPickFolder: () => void;
  readonly onHelp: () => void;
}

interface ButtonProps {
  readonly id: string;
  readonly label: string;
  readonly onClick: () => void;
  readonly children: ReactNode;
  readonly disabled?: boolean;
  readonly pressed?: boolean;
}

function Btn({ id, label, onClick, children, disabled, pressed }: ButtonProps) {
  return (
    <button
      type="button"
      className="ghost icon-button"
      data-testid={`ctl-${id}`}
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

const fill = (value: number, max: number) => ({ "--fill": `${max > 0 ? (value / max) * 100 : 0}%` }) as CSSProperties;

export function Controls(p: ControlsProps) {
  const { t } = useT();
  const [open, setOpen] = useState<Open>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(null);
    };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [open]);

  const toggle = (menu: Exclude<Open, null>) => setOpen(open === menu ? null : menu);
  const mark = (at: number | null) => (at !== null && p.duration > 0 ? { left: `${(at / p.duration) * 100}%` } : undefined);
  const VolumeIcon = p.muted || p.volume === 0 ? VolumeX : p.volume < 0.5 ? Volume1 : Volume2;

  return (
    <div
      className="controls"
      data-testid="controls"
      ref={root}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(null);
        }
      }}
    >
      <div className="seek-row">
        <span className="num" data-testid="time-cur">
          {playClock(p.time)}
        </span>
        <div className="seek-wrap">
          <input
            type="range"
            className="slider seek"
            data-testid="seek"
            aria-label={t("player.seek")}
            min={0}
            max={p.duration || 0}
            step={0.1}
            value={Math.min(p.time, p.duration || 0)}
            style={fill(p.time, p.duration)}
            onChange={(e) => p.onSeek(Number(e.target.value))}
          />
          {p.loop.a !== null && <span className="loop-mark" data-testid="loop-a" style={mark(p.loop.a)} />}
          {p.loop.b !== null && <span className="loop-mark" data-testid="loop-b" style={mark(p.loop.b)} />}
        </div>
        <span className="num" data-testid="time-total">
          {playClock(p.duration)}
        </span>
      </div>
      <div className="button-row">
        <Btn id="prev" label={t("player.prev")} onClick={() => p.onVideo(-1)} disabled={!p.hasPrevVideo}>
          <SkipBack className="icon" aria-hidden />
        </Btn>
        <Btn id="play" label={p.paused ? t("player.play") : t("player.pause")} onClick={p.onPlay}>
          {p.paused ? <Play className="icon" aria-hidden /> : <Pause className="icon" aria-hidden />}
        </Btn>
        <Btn id="next" label={t("player.next")} onClick={() => p.onVideo(1)} disabled={!p.hasNextVideo}>
          <SkipForward className="icon" aria-hidden />
        </Btn>
        <Btn id="line-prev" label={t("player.linePrev")} onClick={() => p.onLine(-1)}>
          <ChevronLeft className="icon" aria-hidden />
        </Btn>
        <Btn id="line-next" label={t("player.lineNext")} onClick={() => p.onLine(1)}>
          <ChevronRight className="icon" aria-hidden />
        </Btn>
        <Btn id="mute" label={p.muted ? t("player.unmute") : t("player.mute")} onClick={p.onMute}>
          <VolumeIcon className="icon" aria-hidden />
        </Btn>
        <input
          type="range"
          className="slider volume"
          data-testid="volume"
          aria-label={t("player.volume")}
          min={0}
          max={1}
          step={0.01}
          value={p.muted ? 0 : p.volume}
          style={fill(p.muted ? 0 : p.volume, 1)}
          onChange={(e) => p.onVolume(Number(e.target.value))}
        />
        <span className="grow" />
        <div className="pop-host">
          <button type="button" className="ghost" data-testid="ctl-speed" title={t("player.speed")} aria-expanded={open === "speed"} onClick={() => toggle("speed")}>
            <Gauge className="icon" aria-hidden />
            <span className="num" data-testid="speed-value">{p.rate}×</span>
          </button>
          {open === "speed" && (
            <div className="menu-list up" role="menu" data-testid="speed-list">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  role="menuitemradio"
                  aria-checked={s === p.rate}
                  data-testid={`speed-${s}`}
                  onClick={() => {
                    p.onRate(s);
                    setOpen(null);
                  }}
                >
                  {s}×
                </button>
              ))}
            </div>
          )}
        </div>
        <Btn id="loop" label={t("player.loop")} pressed={p.loop.a !== null} onClick={p.onLoop}>
          <Repeat className="icon" aria-hidden />
          {p.loop.a !== null && <span className="loop-badge">{p.loop.b === null ? "A" : "AB"}</span>}
        </Btn>
        <div className="pop-host">
          <button type="button" className="ghost" data-testid="ctl-offset" title={t("player.offset")} aria-expanded={open === "offset"} onClick={() => toggle("offset")}>
            <Captions className="icon" aria-hidden />
            <span className="num" data-testid="offset-value">{formatOffset(p.offsetMs)}</span>
          </button>
          {open === "offset" && (
            <div className="pop up offset-pop" data-testid="offset-pop">
              <button type="button" data-testid="offset-minus" onClick={() => p.onOffset(p.offsetMs - 100)}>
                −0.1 s
              </button>
              <button type="button" data-testid="offset-plus" onClick={() => p.onOffset(p.offsetMs + 100)}>
                +0.1 s
              </button>
              <button type="button" className="ghost" data-testid="offset-reset" disabled={p.offsetMs === 0} onClick={() => p.onOffset(0)}>
                {t("player.offset.reset")}
              </button>
              <span className="hint">{t("player.offset.hint")}</span>
            </div>
          )}
        </div>
        <Btn id="shot" label={p.burnShots ? t("player.shotBurn") : t("player.shot")} onClick={p.onShot}>
          <Camera className="icon" aria-hidden />
        </Btn>
        <Btn id="pip" label={t("player.pip")} onClick={p.onPip}>
          <PictureInPicture2 className="icon" aria-hidden />
        </Btn>
        <Btn id="fs" label={p.fullscreen ? t("player.fsExit") : t("player.fs")} onClick={p.onFullscreen}>
          {p.fullscreen ? <Minimize className="icon" aria-hidden /> : <Maximize className="icon" aria-hidden />}
        </Btn>
        <div className="pop-host">
          <button type="button" className="ghost icon-button" data-testid="ctl-more" title={t("player.more")} aria-label={t("player.more")} aria-expanded={open === "more"} onClick={() => toggle("more")}>
            <Ellipsis className="icon" aria-hidden />
          </button>
          {open === "more" && (
            <div className="menu-list up wide" role="menu" data-testid="more-list">
              <button type="button" role="menuitemcheckbox" aria-checked={p.burnShots} data-testid="opt-burn" onClick={() => p.onBurnShots(!p.burnShots)}>
                <span className="check">{p.burnShots ? "✓" : ""}</span>{t("player.opt.burnShots")}
              </button>
              <button type="button" role="menuitemcheckbox" aria-checked={p.fsOverlay} data-testid="opt-overlay" onClick={() => p.onFsOverlay(!p.fsOverlay)}>
                <span className="check">{p.fsOverlay ? "✓" : ""}</span>{t("player.opt.overlay")}
              </button>
              <button type="button" role="menuitem" data-testid="opt-folder" onClick={p.onPickFolder} title={p.outputDir || t("player.opt.folderTitle")}>
                <FolderOpen className="icon" aria-hidden />
                <span className="folder-name">{t("player.opt.folder", { folder: p.outputDir ? p.outputDir : t("player.opt.folderDefault") })}</span>
              </button>
              <button type="button" role="menuitem" data-testid="opt-help" onClick={() => {
                setOpen(null);
                p.onHelp();
              }}>
                {t("player.opt.help")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
