import { Cpu, FileBadge, HardDrive, Languages, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import type { Backend } from "../api/client";
import { useT } from "../i18n/I18nProvider";
import type { PlainKey } from "../i18n";
import { useDownloads } from "../manage/useDownloads";
import { ModelsSection } from "../models-page/ModelsSection";
import { StorageCard } from "../models-page/StorageCard";
import { HardwareSection } from "./HardwareSection";
import { LanguageSection } from "./LanguageSection";
import { LicensesSection } from "./LicensesSection";
import { LlmSection } from "./LlmSection";
import { UpdateSection } from "./UpdateSection";

export type Section = "models" | "hardware" | "llm" | "licenses" | "update" | "language";

/** A label is a literal until its wave moves it into the catalog, then a `key`. */
type NavItem = { id: Section; icon: typeof Cpu } & ({ label: string } | { key: PlainKey });

const SECTIONS: readonly NavItem[] = [
  { id: "models", label: "模型與執行環境", icon: HardDrive },
  { id: "hardware", label: "硬體與效能", icon: Cpu },
  { id: "llm", label: "LLM 來源", icon: Sparkles },
  { id: "licenses", label: "第三方授權", icon: FileBadge },
  { id: "update", label: "檢查更新", icon: RefreshCw },
  { id: "language", key: "language.nav", icon: Languages },
];

export function SettingsPage({ backend, initial = "models" }: { backend: Backend; initial?: Section }) {
  const { t } = useT();
  const [section, setSection] = useState<Section>(initial);
  const [folderKey, setFolderKey] = useState(0);
  const downloads = useDownloads(backend);
  return (
    <div className="settings-page" data-testid="settings-page">
      <nav className="settings-nav" aria-label="設定">
        <h1>設定</h1>
        {SECTIONS.map((item) => {
          const { id, icon: Icon } = item;
          return (
            <button
              key={id}
              type="button"
              className="nav-item"
              aria-current={section === id ? "page" : undefined}
              data-testid={`section-${id}`}
              onClick={() => setSection(id)}
            >
              <Icon className="icon" aria-hidden />
              {"key" in item ? t(item.key) : item.label}
            </button>
          );
        })}
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
        {section === "update" && <UpdateSection />}
        {section === "language" && <LanguageSection backend={backend} />}
      </div>
    </div>
  );
}
