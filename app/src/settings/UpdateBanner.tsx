import { Download, RotateCw, Sparkles } from "lucide-react";
import { useT } from "../i18n/I18nProvider";
import { word } from "../i18n/notice";
import { type Updates, bannerUpdate } from "./useUpdates";
import { stalledDownload } from "./update";
import { workReason } from "./work";

/** The offer of a newer version that the check at start found. It installs nothing until a click. */
export function UpdateBanner({ updates }: { updates: Updates }) {
  const { t, locale } = useT();
  const update = bannerUpdate(updates.state);
  if (!update) return null;
  const { phase } = updates.state;
  const blocked = updates.work !== null ? workReason(updates.work, t) : null;
  const headline =
    phase.kind === "installing"
      ? t("update.installing")
      : phase.kind === "downloading"
      ? t("update.downloading", { version: update.version })
      : phase.kind === "downloaded"
        ? t("update.downloaded", { version: update.version })
        : update.current
          ? t("update.availableFrom", { version: update.version, current: update.current })
          : t("update.available", { version: update.version });
  const offering = phase.kind === "available" || phase.kind === "failed";
  return (
    <section className="update-banner" data-testid="update-banner" aria-label={t("autoUpdate.banner.label")}>
      <span className="badge-icon" aria-hidden>
        <Sparkles />
      </span>
      <div className="update-banner-body">
        <p className="update-banner-head" role="status" aria-live="polite">
          {headline}
        </p>
        {update.notes && (
          <div className="update-banner-notes" data-testid="update-banner-notes">
            <span className="eyebrow">{t("autoUpdate.banner.notes")}</span>
            <p>{update.notes}</p>
          </div>
        )}
        {phase.kind === "failed" && (
          <p className="note bad" role="alert" data-testid="update-banner-failed">
            {phase.reason ? word(phase.reason, locale) : t("errors.updateIncomplete")}
          </p>
        )}
        {phase.kind === "failed" && stalledDownload(phase.reason) && (
          <p className="muted" data-testid="update-banner-retry">
            {t("autoUpdate.retry", { button: t("autoUpdate.banner.install") })}
          </p>
        )}
        {blocked && (offering || phase.kind === "downloaded") && (
          <p className="muted" data-testid="update-banner-blocked">
            {blocked}
          </p>
        )}
      </div>
      <div className="update-banner-actions">
        {offering && (
          <button type="button" className="primary" data-testid="update-banner-install" disabled={blocked !== null} onClick={() => void updates.downloadAndInstall()}>
            <Download className="icon" aria-hidden />
            {t("autoUpdate.banner.install")}
          </button>
        )}
        {phase.kind === "downloaded" && (
          <button type="button" className="primary" data-testid="update-banner-install-now" disabled={blocked !== null} onClick={() => void updates.install()}>
            <RotateCw className="icon" aria-hidden />
            {t("update.install")}
          </button>
        )}
        {phase.kind !== "downloading" && phase.kind !== "installing" && (
          <>
            <button type="button" className="ghost" data-testid="update-banner-later" onClick={updates.later}>
              {t("autoUpdate.banner.later")}
            </button>
            <button type="button" className="ghost" data-testid="update-banner-skip" onClick={updates.skip}>
              {t("autoUpdate.banner.skip")}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
