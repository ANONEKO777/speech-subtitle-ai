import { useEffect, useState } from "react";
import type { Backend } from "../api/client";
import { useT } from "../i18n/I18nProvider";
import { fetchLicenses } from "../manage/api";
import { ExternalLink } from "../manage/ExternalLink";
import { shortVersion } from "../manage/format";
import type { LicenseEntry } from "../manage/types";

export const PROJECT_URL = "https://github.com/ANONEKO777/speech-subtitle-ai";
const FFMPEG_SOURCE_URL = "https://github.com/FFmpeg/FFmpeg/tree/a35157abb96167fd7308edc92b55408d5bb084b0";
const FFMPEG_BUILD_URL = "https://github.com/BtbN/FFmpeg-Builds";
const FFMPEG_SOURCE_LABEL = "FFmpeg a35157abb9";
const LGPL_URL = "https://spdx.org/licenses/LGPL-3.0-or-later.html";
const AGPL_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html";

function BundledNotice() {
  const { t } = useT();
  return (
    <div className="note" data-testid="bundled-notice">
      <p>
        {t("lic.program.pre")}
        <ExternalLink href={AGPL_URL}>AGPL-3.0-or-later</ExternalLink>
        {t("lic.program.post")}{" "}
        <ExternalLink href={PROJECT_URL} testId="project-source-link">
          {PROJECT_URL}
        </ExternalLink>
      </p>
      <p data-testid="ffmpeg-notice">
        {t("lic.ffmpeg.a")}
        <ExternalLink href={LGPL_URL}>LGPL-3.0-or-later</ExternalLink>
        {t("lic.ffmpeg.b")}
        <ExternalLink href={FFMPEG_SOURCE_URL}>{FFMPEG_SOURCE_LABEL}</ExternalLink>
        {t("lic.ffmpeg.c")}
        <ExternalLink href={FFMPEG_BUILD_URL}>BtbN/FFmpeg-Builds</ExternalLink>
        {t("lic.ffmpeg.d")}
      </p>
    </div>
  );
}

export function LicensesSection({ backend }: { backend: Backend }) {
  const { t } = useT();
  const [entries, setEntries] = useState<readonly LicenseEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void fetchLicenses(backend).then(setEntries, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [backend]);
  return (
    <section className="panel" data-testid="licenses-section" aria-labelledby="lic-title">
      <div className="panel-head">
        <div>
          <h2 id="lic-title">{t("lic.title")}</h2>
          <p className="muted">{t("lic.hint")}</p>
        </div>
      </div>
      <BundledNotice />
      {error && (
        <p className="note bad" role="alert">
          {error}
        </p>
      )}
      {entries && (
        <div className="table-wrap">
          <table className="inv" data-testid="licenses-table">
            <thead>
              <tr>
                <th>{t("lic.name")}</th>
                <th>{t("lic.version")}</th>
                <th>{t("lic.license")}</th>
                <th>{t("lic.links")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} data-testid={`lic-${e.id}`}>
                  <td className="name-cell">
                    <span className="asset-id">{e.id}</span>
                    <span className="sub">{e.type === "model" ? t("asset.model") : t("asset.program")}</span>
                  </td>
                  <td title={e.version}>{shortVersion(e.version)}</td>
                  <td data-testid={`lic-${e.id}-name`}>{e.license}</td>
                  <td className="links">
                    <ExternalLink href={e.licenseUrl} testId={`lic-${e.id}-link`}>
                      {t("lic.fullText")}
                    </ExternalLink>
                    {e.parts.map((p) => (
                      <ExternalLink key={p.id} href={p.url}>
                        {p.id}
                      </ExternalLink>
                    ))}
                    <ExternalLink href={e.sourceUrl}>{t("lic.source")}</ExternalLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
