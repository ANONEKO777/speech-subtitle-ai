import { useEffect, useState } from "react";
import type { Backend } from "../api/client";
import { fetchLicenses } from "../manage/api";
import { ExternalLink } from "../manage/ExternalLink";
import { shortVersion } from "../manage/format";
import type { LicenseEntry } from "../manage/types";

export const PROJECT_URL = "https://cggitlab.chinesegamer.net/abcd1997/speech-subtitle-ai";
const FFMPEG_SOURCE_URL = "https://github.com/FFmpeg/FFmpeg/tree/a35157abb96167fd7308edc92b55408d5bb084b0";
const FFMPEG_BUILD_URL = "https://github.com/BtbN/FFmpeg-Builds";
const LGPL_URL = "https://spdx.org/licenses/LGPL-3.0-or-later.html";
const AGPL_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html";

function BundledNotice() {
  return (
    <div className="note" data-testid="bundled-notice">
      <p>
        本程式以 <ExternalLink href={AGPL_URL}>AGPL-3.0-or-later</ExternalLink> 授權。原始碼：{" "}
        <ExternalLink href={PROJECT_URL} testId="project-source-link">
          {PROJECT_URL}
        </ExternalLink>
      </p>
      <p data-testid="ffmpeg-notice">
        安裝程式隨附 FFmpeg 8.1（<ExternalLink href={LGPL_URL}>LGPL-3.0-or-later</ExternalLink>
        組建，未含 GPL 或 nonfree 元件），以獨立的 ffmpeg.exe 與 DLL 放在安裝資料夾的 ffmpeg 子資料夾，可自行替換。FFmpeg
        原始碼：<ExternalLink href={FFMPEG_SOURCE_URL}>FFmpeg a35157abb9</ExternalLink>，組建腳本：
        <ExternalLink href={FFMPEG_BUILD_URL}>BtbN/FFmpeg-Builds</ExternalLink>。完整聲明在安裝資料夾的 THIRD_PARTY.md。
      </p>
    </div>
  );
}

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
