import { Moon, Power } from "lucide-react";
import { useEffect, useState } from "react";
import type { PlainKey } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import { type Countdown, type PowerAction, secondsLeft } from "./model";

/** The sentence around the seconds left, and the cancel button, for each power action. */
const TEXT: Record<PowerAction, { readonly before: PlainKey; readonly cancel: PlainKey }> = {
  sleep: { before: "batch.countdown.sleepBefore", cancel: "batch.countdown.cancelSleep" },
  shutdown: { before: "batch.countdown.shutdownBefore", cancel: "batch.countdown.cancelShutdown" },
};

export function CountdownModal({ countdown, onCancel }: { countdown: Countdown; onCancel: () => void }) {
  const { t, plural } = useT();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, []);
  const left = secondsLeft(countdown.deadlineMs, now);
  const sleep = countdown.action === "sleep";
  const text = TEXT[countdown.action];
  return (
    <div className="modal" role="alertdialog" aria-label={t("batch.countdown.aria")} data-testid="countdown">
      <div className="modal-card countdown-card">
        {sleep ? <Moon className="countdown-icon" aria-hidden /> : <Power className="countdown-icon" aria-hidden />}
        <h2>{t("batch.countdown.title")}</h2>
        <p>
          {t(text.before)}{" "}
          <b className="countdown-num" data-testid="countdown-seconds">
            {left}
          </b>{" "}
          {sleep ? plural("batch.countdown.sleepAfter", left) : plural("batch.countdown.shutdownAfter", left)}
        </p>
        <div className="bar">
          <div className="bar-fill" style={{ width: `${Math.min(100, (left / 60) * 100)}%` }} />
        </div>
        <button type="button" className="primary" data-testid="countdown-cancel" onClick={onCancel} autoFocus>
          {t(text.cancel)}
        </button>
      </div>
    </div>
  );
}
