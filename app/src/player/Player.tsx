import { convertFileSrc } from "@tauri-apps/api/core";
import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import type { Backend, LanguageInfo } from "../api/client";
import { type Loaded, useCueEditing } from "../editor/useCueEditing";
import { exportItems, shortName } from "../export/exports";
import type { Settings } from "../settings/settings";
import { useSummary } from "../summary/useSummary";
import { SidePanel, type Tab } from "./SidePanel";
import type { Cue } from "./cues";
import { useActiveCue } from "./useActiveCue";

interface Props {
  readonly backend: Backend;
  readonly projectId: string;
  readonly videoPath: string;
  readonly settings: Settings;
  readonly languages: readonly LanguageInfo[];
  readonly lang: string;
  readonly onLang: (code: string) => void;
  readonly loaded: Loaded;
  /** What the last run did with the person's edits, shown until something else happens. */
  readonly notice: string | null;
}

function extension(path: string): string {
  return path.slice(path.lastIndexOf(".") + 1).toLowerCase();
}

/** A seek lands on the frame at or before the target. Aiming a few frames into the cue makes that frame belong to the cue, so its subtitle shows. */
const SEEK_NUDGE_MS = 50;

const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));

export function Player({ backend, projectId, videoPath, settings, languages, lang, onLang, loaded, notice }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [unplayable, setUnplayable] = useState(false);
  const [tab, setTab] = useState<Tab>("cues");
  const [status, setStatus] = useState<string | null>(notice);
  const editing = useCueEditing(backend, projectId, lang, loaded);
  const summary = useSummary(backend, projectId, lang);
  const cues = editing.state.cues;
  const active = useActiveCue(video, cues);
  const cue = active >= 0 ? cues[active] : undefined;

  useEffect(() => setStatus(notice), [notice]);

  const undo = editing.undo;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z" && !typing(e.target)) {
        e.preventDefault();
        void undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo]);

  const seekMs = useCallback((ms: number) => {
    if (video.current) video.current.currentTime = ms / 1000;
  }, []);
  const seekCue = useCallback((c: Cue) => seekMs(Math.min(c.startMs + SEEK_NUDGE_MS, c.endMs - 1)), [seekMs]);
  const seekChapter = useCallback(
    (seconds: number) => {
      seekMs(seconds * 1000);
      setTab("cues");
    },
    [seekMs],
  );

  const label = shortName(languages.find((l) => l.code === lang)?.nativeName ?? lang);
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
        summary={summary}
        exports={exportItems(videoPath, lang, label)}
        status={status}
        onStatus={setStatus}
        onSeekCue={seekCue}
        onSeekSeconds={seekChapter}
      />
    </div>
  );
}
