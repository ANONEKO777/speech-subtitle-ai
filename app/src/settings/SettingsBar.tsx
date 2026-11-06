import { ALargeSmall, ArrowUpDown, type LucideIcon, Palette, UnfoldVertical } from "lucide-react";
import type { CSSProperties } from "react";
import type { SubtitleMode } from "../player/cues";
import type { Settings } from "./settings";

const MODES: ReadonlyArray<readonly [SubtitleMode, string]> = [
  ["en", "英文"],
  ["zh", "中文"],
  ["both", "雙語"],
];

interface SliderProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly testid?: string;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly value: number;
  readonly shown: string;
  readonly onChange: (value: number) => void;
}

function Slider({ icon: Icon, label, testid, min, max, step, value, shown, onChange }: SliderProps) {
  const fill = { "--fill": `${((value - min) / (max - min)) * 100}%` } as CSSProperties;
  return (
    <label className="control" title={label}>
      <Icon className="icon" aria-hidden />
      <input
        type="range"
        className="slider"
        aria-label={label}
        data-testid={testid}
        min={min}
        max={max}
        step={step}
        value={value}
        style={fill}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="num">{shown}</span>
    </label>
  );
}

interface Props {
  readonly settings: Settings;
  readonly onChange: (next: Settings) => void;
}

export function SettingsBar({ settings, onChange }: Props) {
  const set = (patch: Partial<Settings>) => onChange({ ...settings, ...patch });
  return (
    <div className="settings">
      <div className="seg" role="group" aria-label="字幕語言">
        {MODES.map(([mode, label]) => (
          <button
            key={mode}
            type="button"
            data-testid={`mode-${mode}`}
            aria-pressed={settings.mode === mode}
            onClick={() => set({ mode })}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="tools">
        <Slider
          icon={ALargeSmall}
          label="字幕大小"
          testid="font-size"
          min={14}
          max={64}
          value={settings.fontSize}
          shown={String(settings.fontSize)}
          onChange={(fontSize) => set({ fontSize })}
        />
        <label className="control" title="字幕顏色">
          <Palette className="icon" aria-hidden />
          <input
            type="color"
            className="swatch"
            aria-label="字幕顏色"
            data-testid="font-color"
            value={settings.color}
            onChange={(e) => set({ color: e.target.value })}
          />
        </label>
        <Slider
          icon={UnfoldVertical}
          label="行距"
          min={1}
          max={2.2}
          step={0.1}
          value={settings.lineHeight}
          shown={settings.lineHeight.toFixed(1)}
          onChange={(lineHeight) => set({ lineHeight })}
        />
        <label className="control toggle" title="雙語時中文放在英文上方">
          <ArrowUpDown className="icon" aria-hidden />
          <span className="collapsible">中文在上</span>
          <input
            type="checkbox"
            role="switch"
            className="switch"
            checked={settings.zhFirst}
            onChange={(e) => set({ zhFirst: e.target.checked })}
          />
        </label>
      </div>
    </div>
  );
}
