import { ALargeSmall, ArrowUpDown, type LucideIcon, Palette, UnfoldVertical } from "lucide-react";
import { type CSSProperties, useState } from "react";
import type { Translate } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import type { SubtitleMode } from "../player/cues";
import { CutName } from "./CutName";
import type { Settings } from "./settings";

/** Stands in for the name while the sentence around it is read, so the name alone can be shortened. */
const NAME_HERE = "{name}";

const modes = (langName: string, t: Translate): ReadonlyArray<readonly [SubtitleMode, string]> => [
  ["en", t("bar.original")],
  ["zh", langName],
  ["both", t("bar.both")],
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
    <label className="control range" title={label}>
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
  /** The name of the language shown, such as 繁體中文. */
  readonly langName: string;
  readonly settings: Settings;
  readonly onChange: (next: Settings) => void;
}

export function SettingsBar({ langName, settings, onChange }: Props) {
  const { t } = useT();
  const set = (patch: Partial<Settings>) => onChange({ ...settings, ...patch });
  const [beforeName, afterName] = t("bar.first", { name: NAME_HERE }).split(NAME_HERE);
  const [wordsCut, setWordsCut] = useState(false);
  return (
    <div className="settings">
      <div className="seg" role="group" aria-label={t("bar.language")}>
        {modes(langName, t).map(([mode, label]) => (
          <button
            key={mode}
            type="button"
            data-testid={`mode-${mode}`}
            className={mode === "zh" ? "seg-name" : undefined}
            aria-pressed={settings.mode === mode}
            onClick={() => set({ mode })}
          >
            {mode === "zh" ? <CutName name={label} tip /> : label}
          </button>
        ))}
      </div>
      <div className="tools">
        <Slider
          icon={ALargeSmall}
          label={t("bar.size")}
          testid="font-size"
          min={14}
          max={64}
          value={settings.fontSize}
          shown={String(settings.fontSize)}
          onChange={(fontSize) => set({ fontSize })}
        />
        <label className="control" title={t("bar.color")}>
          <Palette className="icon" aria-hidden />
          <input
            type="color"
            className="swatch"
            aria-label={t("bar.color")}
            data-testid="font-color"
            value={settings.color}
            onChange={(e) => set({ color: e.target.value })}
          />
        </label>
        <Slider
          icon={UnfoldVertical}
          label={t("bar.lineHeight")}
          min={1}
          max={2.2}
          step={0.1}
          value={settings.lineHeight}
          shown={settings.lineHeight.toFixed(1)}
          onChange={(lineHeight) => set({ lineHeight })}
        />
        <label className="control toggle" title={t("bar.firstTitle", { name: langName })}>
          <ArrowUpDown className="icon" aria-hidden />
          <CutName className="collapsible first-words" name={langName} before={beforeName} after={afterName} onCut={setWordsCut} />
          <input
            type="checkbox"
            role="switch"
            className="switch"
            // shortened words are laid out in pieces, which a screen reader would read with gaps between them
            aria-label={wordsCut ? t("bar.first", { name: langName }) : undefined}
            checked={settings.zhFirst}
            onChange={(e) => set({ zhFirst: e.target.checked })}
          />
        </label>
      </div>
    </div>
  );
}
