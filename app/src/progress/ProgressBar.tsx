import { useT } from "../i18n/I18nProvider";
import { ADD_TARGET_STEPS, type JobView, STEPS, stepLabel } from "./job";

interface Props {
  readonly view: JobView;
  /** The name of the language the run translates into. */
  readonly target: string;
  /** The project already has its speech steps, so this run only translates again into `target`. */
  readonly addsTarget?: boolean;
}

export function ProgressBar({ view, target, addsTarget = false }: Props) {
  const { t } = useT();
  const running = view.kind === "running" ? view : null;
  const percent = Math.round((view.kind === "done" ? 1 : (running?.overall ?? 0)) * 100);
  const stepIndex = running?.step ? STEPS.indexOf(running.step) + 1 : 0;
  const label = running?.step
    ? t("progress.stepOf", { label: stepLabel(running.step, target, t), index: stepIndex, total: STEPS.length })
    : view.kind === "waiting"
      ? t("progress.waiting")
      : "";
  return (
    <div className="progress">
      <div className="progress-head">
        <span className="step-name" data-testid="step-name">
          {label}
        </span>
        <span className="percent" data-testid="percent">
          {percent}%
        </span>
      </div>
      <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="bar-fill" style={{ width: `${percent}%` }} />
      </div>
      {addsTarget && (
        <p className="progress-note" data-testid="rerun-note">
          {t("progress.rerun", { target })}
        </p>
      )}
      <ol className="steps">
        {STEPS.map((step, i) => (
          <li
            key={step}
            data-state={view.kind === "done" || i + 1 < stepIndex ? "done" : i + 1 === stepIndex ? "current" : "todo"}
            data-kept={addsTarget && !ADD_TARGET_STEPS.includes(step)}
          >
            {stepLabel(step, target, t)}
          </li>
        ))}
      </ol>
    </div>
  );
}
