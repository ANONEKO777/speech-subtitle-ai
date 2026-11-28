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
import type { Updates } from "./useUpdates";

export type Section = "models" | "hardware" | "llm" | "licenses" | "update" | "language";

type NavItem = { id: Section; icon: typeof Cpu; key: PlainKey };

const SECTIONS: readonly NavItem[] = [
  { id: "models", key: "settings.nav.models", icon: HardDrive },
  { id: "hardware", key: "hw.title", icon: Cpu },
  { id: "llm", key: "llm.title", icon: Sparkles },
  { id: "licenses", key: "lic.title", icon: FileBadge },
  { id: "update", key: "update.title", icon: RefreshCw },
  { id: "language", key: "language.nav", icon: Languages },
];

export function SettingsPage({ backend, updates, initial = "models" }: { backend: Backend; updates: Updates; initial?: Section }) {
  const { t } = useT();
  const [section, setSection] = useState<Section>(initial);
  const [folderKey, setFolderKey] = useState(0);
  const downloads = useDownloads(backend);
  return (
    <div className="settings-page" data-testid="settings-page">
      <nav className="settings-nav" aria-label={t("settings.title")}>
        <h1>{t("settings.title")}</h1>
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
              {t(item.key)}
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
        {section === "update" && <UpdateSection updates={updates} />}
        {section === "language" && <LanguageSection backend={backend} />}
      </div>
    </div>
  );
}
