import { Download, RefreshCw, RotateCw } from "lucide-react";
import { useT } from "../i18n/I18nProvider";
import type { Translate } from "../i18n";
import type { Locale } from "../i18n/locale";
import { word } from "../i18n/notice";
import type { Updates, Work } from "./useUpdates";

export const workReason = (work: Exclude<Work, null>, t: Translate): string =>
  work === "job" ? t("autoUpdate.busy.job") : t("autoUpdate.busy.batch");

const when = (at: number, locale: Locale) => new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(at);

function StartCheck({ updates }: { updates: Updates }) {
  const { t, locale } = useT();
  const { build, state, setCheckAtStart } = updates;
  const { prefs } = state;
  const supported = build?.supported ?? false;
  const failure = prefs.lastFailure;
  return (
    <div className="start-check" data-testid="update-at-start">
      <label className="consent">
        <input
          type="checkbox"
          role="switch"
          className="switch"
          data-testid="update-at-start-toggle"
          checked={supported && prefs.checkAtStart}
          disabled={!supported}
          onChange={(e) => setCheckAtStart(e.target.checked)}
        />
        <span>
          <span className="start-check-label">{t("autoUpdate.atStart")}</span>
          <span className="muted">{build && !supported ? t("autoUpdate.unsupported") : t("autoUpdate.atStartHint")}</span>
        </span>
      </label>
      {supported && failure && (
        <p className="muted" data-testid="update-last-failed">
          {t("autoUpdate.lastFailed", { time: when(failure.at, locale), reason: failure.reason ? word(failure.reason, locale) : t("errors.updateIncomplete") })}
        </p>
      )}
      {supported && !failure && prefs.lastCheckAt !== null && (
        <p className="muted" data-testid="update-last-checked">
          {t("autoUpdate.lastChecked", { time: when(prefs.lastCheckAt, locale) })}
        </p>
      )}
    </div>
  );
}

export function UpdateSection({ updates }: { updates: Updates }) {
  const { t, locale } = useT();
  const { phase } = updates.state;
  const busy = phase.kind === "checking" || phase.kind === "downloading" || phase.kind === "installing";
  return (
    <section className="panel" data-testid="update-section" aria-labelledby="update-title">
      <div className="panel-head">
        <div>
          <h2 id="update-title">{t("update.title")}</h2>
          <p className="muted">{t("update.hint")}</p>
        </div>
        <button type="button" className="ghost" data-testid="update-check" disabled={busy} onClick={() => void updates.check()}>
          <RefreshCw className="icon" aria-hidden />
          {t("update.check")}
        </button>
      </div>
      <StartCheck updates={updates} />
      <div role="status" aria-live="polite" data-testid="update-status">
        {phase.kind === "checking" && <p className="note">{t("update.checking")}</p>}
        {phase.kind === "upToDate" && (
          <p className="note ok" data-testid="update-uptodate">
            {phase.current ? t("update.upToDateVersion", { version: phase.current }) : t("update.upToDate")}
          </p>
        )}
        {phase.kind === "available" && (
          <div className="note" data-testid="update-available">
            <p>
              {phase.update.current
                ? t("update.availableFrom", { version: phase.update.version, current: phase.update.current })
                : t("update.available", { version: phase.update.version })}
            </p>
            {phase.update.notes && <p className="muted update-notes">{phase.update.notes}</p>}
            <button type="button" className="primary" data-testid="update-download" onClick={() => void updates.download()}>
              <Download className="icon" aria-hidden />
              {t("update.download")}
            </button>
          </div>
        )}
        {phase.kind === "downloading" && <p className="note">{t("update.downloading", { version: phase.update.version })}</p>}
        {phase.kind === "downloaded" && (
          <div className="note ok" data-testid="update-downloaded">
            <p>{t("update.downloaded", { version: phase.update.version })}</p>
            <button
              type="button"
              className="primary"
              data-testid="update-install"
              disabled={updates.work !== null}
              onClick={() => void updates.install()}
            >
              <RotateCw className="icon" aria-hidden />
              {t("update.install")}
            </button>
            {updates.work && (
              <p className="muted" data-testid="update-install-blocked">
                {workReason(updates.work, t)}
              </p>
            )}
          </div>
        )}
        {phase.kind === "installing" && <p className="note">{t("update.installing")}</p>}
        {phase.kind === "failed" && (
          <p className="note bad" role="alert" data-testid="update-failed">
            {phase.reason ? word(phase.reason, locale) : t("errors.updateIncomplete")}
          </p>
        )}
      </div>
    </section>
  );
}
