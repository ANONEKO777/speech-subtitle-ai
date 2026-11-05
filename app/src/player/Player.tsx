import { convertFileSrc } from "@tauri-apps/api/core";
import { type CSSProperties, useCallback, useRef, useState } from "react";
import type { Settings } from "../settings/settings";
import { CueList } from "./CueList";
import type { Cue } from "./cues";
import { useActiveCue } from "./useActiveCue";

interface Props {
  readonly videoPath: string;
  readonly cues: readonly Cue[];
  readonly settings: Settings;
}

function extension(path: string): string {
  return path.slice(path.lastIndexOf(".") + 1).toLowerCase();
}

/** The subtitle box is as tall as a bilingual cue of two lines per language in every mode, so switching the mode never resizes the video. */
const SUBTITLE_LINES = 4;

/** A seek lands on the frame at or before the target. Aiming a few frames into the cue makes that frame belong to the cue, so its subtitle shows. */
const SEEK_NUDGE_MS = 50;

export function Player({ videoPath, cues, settings }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [unplayable, setUnplayable] = useState(false);
  const active = useActiveCue(video, cues);
  const cue = active >= 0 ? cues[active] : undefined;
  const seek = useCallback((c: Cue) => {
    if (video.current) video.current.currentTime = Math.min(c.startMs + SEEK_NUDGE_MS, c.endMs - 1) / 1000;
  }, []);

  const lines: Array<{ lang: "en" | "zh"; text: string }> = [];
  if (cue && settings.mode !== "zh") lines.push({ lang: "en", text: cue.en });
  if (cue && settings.mode !== "en") lines.push({ lang: "zh", text: cue.zh });
  if (settings.zhFirst) lines.reverse();

  const subtitleStyle: CSSProperties = {
    fontSize: settings.fontSize,
    color: settings.color,
    lineHeight: settings.lineHeight,
    height: `${settings.fontSize * settings.lineHeight * SUBTITLE_LINES}px`,
  };

  return (
    <div className="player">
      <div className="stage">
        <video
          key={videoPath}
          ref={video}
          data-testid="video"
          src={convertFileSrc(videoPath)}
          controls
          onError={() => setUnplayable(true)}
        />
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
      <CueList
        cues={cues}
        active={active}
        mode={settings.mode}
        onSeek={seek}
      />
    </div>
  );
}
