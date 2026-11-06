import { type JobView, STEPS, STEP_LABEL } from "./job";

export function ProgressBar({ view }: { view: JobView }) {
  const running = view.kind === "running" ? view : null;
  const percent = Math.round((view.kind === "done" ? 1 : (running?.overall ?? 0)) * 100);
  const stepIndex = running?.step ? STEPS.indexOf(running.step) + 1 : 0;
  const label = running?.step
    ? `${STEP_LABEL[running.step]}（${stepIndex}/${STEPS.length}）`
    : view.kind === "waiting"
      ? "等待後端開始"
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
      <ol className="steps">
        {STEPS.map((step, i) => (
          <li
            key={step}
            data-state={view.kind === "done" || i + 1 < stepIndex ? "done" : i + 1 === stepIndex ? "current" : "todo"}
          >
            {STEP_LABEL[step]}
          </li>
        ))}
      </ol>
    </div>
  );
}
