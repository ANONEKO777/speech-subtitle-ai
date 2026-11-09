import { useEffect, useState } from "react";
import type { Backend } from "../api/client";
import { fetchLicenses } from "../manage/api";
import { ExternalLink } from "../manage/ExternalLink";
import { shortVersion } from "../manage/format";
import type { LicenseEntry } from "../manage/types";

export function LicensesSection({ backend }: { backend: Backend }) {
  const [entries, setEntries] = useState<readonly LicenseEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void fetchLicenses(backend).then(setEntries, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [backend]);
  return (
    <section className="panel" data-testid="licenses-section" aria-labelledby="lic-title">
      <div className="panel-head">
        <div>
          <h2 id="lic-title">第三方授權</h2>
          <p className="muted">App 另外下載的每個模型與執行檔，各自的授權與來源。連結會用瀏覽器開啟。</p>
        </div>
      </div>
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
                <th>名稱</th>
                <th>版本</th>
                <th>授權</th>
                <th>連結</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} data-testid={`lic-${e.id}`}>
                  <td className="name-cell">
                    <span className="asset-id">{e.id}</span>
                    <span className="sub">{e.type === "model" ? "模型" : "執行檔"}</span>
                  </td>
                  <td title={e.version}>{shortVersion(e.version)}</td>
                  <td data-testid={`lic-${e.id}-name`}>{e.license}</td>
                  <td className="links">
                    <ExternalLink href={e.licenseUrl} testId={`lic-${e.id}-link`}>
                      授權全文
                    </ExternalLink>
                    {e.parts.map((p) => (
                      <ExternalLink key={p.id} href={p.url}>
                        {p.id}
                      </ExternalLink>
                    ))}
                    <ExternalLink href={e.sourceUrl}>下載來源</ExternalLink>
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
