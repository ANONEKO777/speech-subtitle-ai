import { Moon, Power } from "lucide-react";
import { useEffect, useState } from "react";
import { type Countdown, secondsLeft } from "./model";

export function CountdownModal({ countdown, onCancel }: { countdown: Countdown; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, []);
  const left = secondsLeft(countdown.deadlineMs, now);
  const sleep = countdown.action === "sleep";
  return (
    <div className="modal" role="alertdialog" aria-label="倒數" data-testid="countdown">
      <div className="modal-card countdown-card">
        {sleep ? <Moon className="countdown-icon" aria-hidden /> : <Power className="countdown-icon" aria-hidden />}
        <h2>佇列已全部完成</h2>
        <p>
          電腦將在{" "}
          <b className="countdown-num" data-testid="countdown-seconds">
            {left}
          </b>{" "}
          秒後{sleep ? "進入睡眠" : "關機"}。
        </p>
        <div className="bar">
          <div className="bar-fill" style={{ width: `${Math.min(100, (left / 60) * 100)}%` }} />
        </div>
        <button type="button" className="primary" data-testid="countdown-cancel" onClick={onCancel} autoFocus>
          取消，不要{sleep ? "睡眠" : "關機"}
        </button>
      </div>
    </div>
  );
}
