import type { SubtitleMode } from "../player/cues";
import type { Settings } from "./settings";

const MODES: ReadonlyArray<readonly [SubtitleMode, string]> = [
  ["en", "英文"],
  ["zh", "中文"],
  ["both", "雙語"],
];

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
      <label>
        大小
        <input
          type="range"
          data-testid="font-size"
          min={14}
          max={64}
          value={settings.fontSize}
          onChange={(e) => set({ fontSize: Number(e.target.value) })}
        />
        <span className="num">{settings.fontSize}</span>
      </label>
      <label>
        顏色
        <input
          type="color"
          data-testid="font-color"
          value={settings.color}
          onChange={(e) => set({ color: e.target.value })}
        />
      </label>
      <label>
        行距
        <input
          type="range"
          min={1}
          max={2.2}
          step={0.1}
          value={settings.lineHeight}
          onChange={(e) => set({ lineHeight: Number(e.target.value) })}
        />
      </label>
      <label title="雙語時中文放在英文上方">
        <input type="checkbox" checked={settings.zhFirst} onChange={(e) => set({ zhFirst: e.target.checked })} />
        中文在上
      </label>
    </div>
  );
}
