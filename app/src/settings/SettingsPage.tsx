import { Cpu, FileBadge, HardDrive, Sparkles } from "lucide-react";
import { useState } from "react";
import type { Backend } from "../api/client";
import { useDownloads } from "../manage/useDownloads";
import { ModelsSection } from "../models-page/ModelsSection";
import { StorageCard } from "../models-page/StorageCard";
import { HardwareSection } from "./HardwareSection";
import { LicensesSection } from "./LicensesSection";
import { LlmSection } from "./LlmSection";

export type Section = "models" | "hardware" | "llm" | "licenses";

const SECTIONS: readonly { id: Section; label: string; icon: typeof Cpu }[] = [
  { id: "models", label: "模型與執行環境", icon: HardDrive },
  { id: "hardware", label: "硬體與效能", icon: Cpu },
  { id: "llm", label: "LLM 來源", icon: Sparkles },
  { id: "licenses", label: "第三方授權", icon: FileBadge },
];

export function SettingsPage({ backend, initial = "models" }: { backend: Backend; initial?: Section }) {
  const [section, setSection] = useState<Section>(initial);
  const [folderKey, setFolderKey] = useState(0);
  const downloads = useDownloads(backend);
  return (
    <div className="settings-page" data-testid="settings-page">
      <nav className="settings-nav" aria-label="設定">
        <h1>設定</h1>
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className="nav-item"
            aria-current={section === id ? "page" : undefined}
            data-testid={`section-${id}`}
            onClick={() => setSection(id)}
          >
            <Icon className="icon" aria-hidden />
            {label}
          </button>
        ))}
      </nav>
      <div className="settings-body">
        {section === "models" && (
          <>
            <StorageCard backend={backend} onChanged={() => setFolderKey((k) => k + 1)} />
            <ModelsSection key={folderKey} backend={backend} downloads={downloads} />
          </>
        )}
        {section === "hardware" && <HardwareSection backend={backend} downloads={downloads} onOpenLlm={() => setSection("llm")} />}
        {section === "llm" && <LlmSection backend={backend} />}
        {section === "licenses" && <LicensesSection backend={backend} />}
      </div>
    </div>
  );
}
