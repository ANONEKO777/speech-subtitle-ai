import { useT } from "../i18n/I18nProvider";
import { fraction, isActive, stateLabel } from "./downloads";
import { bytes, speed } from "./format";
import type { DownloadJob } from "./types";
import { word } from "../i18n/notice";

/** One download: name, a bar, bytes, speed, and the reason when it failed. */
export function JobRow({ job, testId }: { job: DownloadJob; testId: string }) {
  const { t, plural, locale } = useT();
  const percent = Math.round(fraction(job) * 100);
  return (
    <div className="job" data-testid={testId} data-state={job.state}>
      <div className="job-head">
        <span className="job-name">{job.assetId}</span>
        <span className="job-state">{stateLabel(job, t)}</span>
      </div>
      <div className="mbar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="job-meta">
        <span data-testid={`${testId}-percent`}>{percent}%</span>
        <span>
          {bytes(job.bytesDone, locale)} / {bytes(job.bytesTotal, locale)}
        </span>
        {isActive(job) && <span data-testid={`${testId}-speed`}>{speed(job.speedBps, locale)}</span>}
        {job.resumedFrom > 0 && <span>{t("download.resumedFrom", { size: bytes(job.resumedFrom, locale) })}</span>}
        {job.retries > 0 && isActive(job) && <span>{plural("download.retries", job.retries)}</span>}
      </div>
      {job.failure && (
        <p className="note bad" role="alert" data-testid={`${testId}-error`}>
          {word(job.failure.message, locale)}
        </p>
      )}
    </div>
  );
}
