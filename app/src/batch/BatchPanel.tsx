import {
  CirclePause,
  CirclePlay,
  GripVertical,
  ListPlus,
  Moon,
  Power,
  RotateCcw,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import { type PointerEvent, useEffect, useRef, useState } from "react";
import type { Backend, LanguageInfo } from "../api/client";
import {
  type ItemAction,
  itemAction,
  putSettings,
  removeFinished,
  removeItem,
  reorderQueue,
  setQueuePaused,
} from "./api";
import { DEFAULT_SOURCE, sourceTag } from "../api/sourceLang";
import type { PlainKey } from "../i18n";
import { useT } from "../i18n/I18nProvider";
import { isExperimental, langName } from "./lang";
import {
  type Batch,
  type BatchItem,
  type ItemState,
  type OnDone,
  type PowerAction,
  STEP_NAME,
  STEP_ORDER,
  actionsFor,
  formatEta,
  isFinished,
  moveId,
  overall,
  slotAt,
} from "./model";
import { baseName } from "./paths";
import { LinkedText } from "../manage/LinkedText";

const STATE_LABEL: Record<ItemState, PlainKey> = {
  queued: "batch.state.queued",
  running: "batch.state.running",
  paused: "batch.state.paused",
  done: "batch.state.done",
  failed: "batch.state.failed",
  cancelled: "batch.state.cancelled",
};

interface Props {
  readonly backend: Backend;
  readonly batch: Batch;
  readonly languages: readonly LanguageInfo[];
  readonly onOpen: (item: BatchItem) => void;
  readonly onAdd: () => void;
  readonly onError: (message: string) => void;
}

interface Drag {
  readonly id: string;
  readonly from: number;
  readonly slot: number;
  /** Vertical middle of every other row when the drag began. */
  readonly middles: readonly number[];
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function BatchPanel({ backend, batch, languages, onOpen, onAdd, onError }: Props) {
  const { t } = useT();
  const total = overall(batch.items);
  const run = (p: Promise<unknown>) => void p.catch((e: unknown) => onError(message(e)));
  const [drag, setDrag] = useState<Drag | null>(null);
  const list = useRef<HTMLUListElement>(null);

  const ids = batch.items.map((i) => i.id);
  const shown = drag ? moveId(ids, drag.from, drag.slot) : ids;
  const byId = new Map(batch.items.map((i) => [i.id, i]));
  const hasFinished = batch.items.some((i) => isFinished(i.state));

  const gesture = useRef<Drag | null>(null);
  const live = useRef({ backend, ids });
  live.current = { backend, ids };
  const dragId = drag?.id;

  // The row's node is re-inserted when it moves down the list, which drops any pointer capture, so
  // the gesture follows the pointer on window instead of on the handle.
  useEffect(() => {
    if (dragId === undefined) return;
    const end = (commit: boolean) => {
      const g = gesture.current;
      gesture.current = null;
      if (commit && g && g.slot !== g.from && live.current.ids[g.from] === g.id) {
        run(reorderQueue(live.current.backend, moveId(live.current.ids, g.from, g.slot)));
      }
      setDrag(null);
    };
    const onMove = (e: globalThis.PointerEvent) => {
      const g = gesture.current;
      if (!g) return;
      const next = { ...g, slot: slotAt(g.middles, e.clientY) };
      gesture.current = next;
      setDrag(next);
    };
    const onUp = () => end(true);
    const onCancel = () => end(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    window.addEventListener("blur", onCancel);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      window.removeEventListener("blur", onCancel);
    };
  }, [dragId]);

  const startDrag = (e: PointerEvent<HTMLElement>, id: string) => {
    if (e.button !== 0) return;
    const rows = [...(list.current?.querySelectorAll<HTMLElement>("[data-row-id]") ?? [])];
    const middles = rows
      .filter((r) => r.dataset["rowId"] !== id)
      .map((r) => r.getBoundingClientRect().top + r.offsetHeight / 2);
    const from = ids.indexOf(id);
    const next = { id, from, slot: from, middles };
    gesture.current = next;
    setDrag(next);
  };
  const nudge = (id: string, by: -1 | 1) => {
    const from = ids.indexOf(id);
    const to = from + by;
    if (to >= 0 && to < ids.length) run(reorderQueue(backend, moveId(ids, from, to)));
  };

  const act = (item: BatchItem, a: ItemAction | "remove") =>
    run(a === "remove" ? removeItem(backend, item.id) : itemAction(backend, item.id, a));

  return (
    <section className="batch" data-testid="batch-panel" data-link={batch.link}>
      <div className="batch-head">
        <div className="batch-summary" data-testid="batch-summary">
          <strong data-testid="batch-count">
            {total.finished}/{total.total}
          </strong>
          <span>{t("batch.processed")}</span>
          <span className="batch-eta" data-testid="batch-eta">
            {total.etaS !== null ? t("batch.left", { eta: formatEta(total.etaS, t) }) : total.active ? t("batch.etaLater") : ""}
          </span>
        </div>
        <div className="batch-tools">
          <button type="button" data-testid="batch-add" onClick={onAdd}>
            <ListPlus className="icon" aria-hidden />
            {t("batch.add")}
          </button>
          <button
            type="button"
            data-testid="batch-pause"
            title={batch.paused ? t("batch.resumeTitle") : t("batch.pauseTitle")}
            onClick={() => run(setQueuePaused(backend, !batch.paused))}
          >
            {batch.paused ? <CirclePlay className="icon" aria-hidden /> : <CirclePause className="icon" aria-hidden />}
            {batch.paused ? t("batch.resume") : t("batch.pause")}
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="batch-clear"
            disabled={!hasFinished}
            onClick={() => run(removeFinished(backend))}
          >
            <Trash2 className="icon" aria-hidden />
            {t("batch.clear")}
          </button>
        </div>
        <div
          className="bar batch-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(total.fraction * 100)}
          data-testid="batch-overall"
        >
          <div className="bar-fill" style={{ width: `${Math.round(total.fraction * 100)}%` }} />
        </div>
      </div>
      {batch.link !== "live" && batch.loaded && (
        <p className="batch-link" role="status" data-testid="batch-link">
          <TriangleAlert className="icon" aria-hidden />
          {t("batch.reconnecting")}
        </p>
      )}
      {batch.paused && (
        <p className="batch-note" data-testid="batch-paused-note">
          {t("batch.pausedNote")}
        </p>
      )}
      {batch.items.length === 0 ? (
        <p className="batch-empty" data-testid="batch-empty">
          {t("batch.empty")}
        </p>
      ) : (
        <ul className="batch-list" ref={list} data-testid="batch-list" data-dragging={drag !== null}>
          {shown.map((id, at) => {
            const item = byId.get(id);
            if (!item) return null;
            const before = byId.get(shown[at - 1] ?? "");
            return (
              <Row
                key={id}
                item={item}
                nextTarget={before !== undefined && before.videoPath === item.videoPath && before.sourceLang === item.sourceLang}
                languages={languages}
                dragging={drag?.id === id}
                canDrag={item.state === "queued" || item.state === "paused"}
                onOpen={() => onOpen(item)}
                onAct={(a) => act(item, a)}
                onDragStart={(e) => startDrag(e, id)}
                onNudge={(by) => nudge(id, by)}
              />
            );
          })}
        </ul>
      )}
      <OnDoneSetting backend={backend} batch={batch} onError={onError} />
    </section>
  );
}

interface RowProps {
  readonly item: BatchItem;
  /** The row above is the same video in another language, so this is one more target of it. */
  readonly nextTarget: boolean;
  readonly languages: readonly LanguageInfo[];
  readonly dragging: boolean;
  readonly canDrag: boolean;
  readonly onOpen: () => void;
  readonly onAct: (a: ItemAction | "remove") => void;
  readonly onDragStart: (e: PointerEvent<HTMLElement>) => void;
  readonly onNudge: (by: -1 | 1) => void;
}

const ACTION = {
  pause: { label: "batch.action.pause", icon: CirclePause },
  resume: { label: "batch.action.resume", icon: CirclePlay },
  cancel: { label: "common.cancel", icon: X },
  retry: { label: "batch.action.retry", icon: RotateCcw },
  remove: { label: "batch.action.remove", icon: Trash2 },
} as const satisfies Record<string, { label: PlainKey; icon: unknown }>;

function Row({ item, nextTarget, languages, dragging, canDrag, onOpen, onAct, onDragStart, onNudge }: RowProps) {
  const { t, locale } = useT();
  const percent = Math.round(item.progress * 100);
  const stepIndex = item.step ? STEP_ORDER.indexOf(item.step) + 1 : 0;
  const detail =
    item.state === "running"
      ? item.step
        ? t("batch.stepOf", { step: t(STEP_NAME[item.step]), i: stepIndex, n: STEP_ORDER.length })
        : t("batch.preparing")
      : item.state === "queued" && item.attempts > 0
        ? t("batch.retryWaiting")
        : "";
  return (
    <li className="batch-row" data-row-id={item.id} data-testid={`qrow-${item.id}`} data-state={item.state} data-next-target={nextTarget} data-dragging={dragging}>
      <button
        type="button"
        className="ghost icon-button drag-handle"
        data-testid={`qdrag-${item.id}`}
        aria-label={t("batch.drag")}
        disabled={!canDrag}
        onPointerDown={canDrag ? onDragStart : undefined}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault();
            onNudge(e.key === "ArrowUp" ? -1 : 1);
          }
        }}
      >
        <GripVertical className="icon" aria-hidden />
      </button>
      <button
        type="button"
        className="ghost batch-name"
        data-testid={`qopen-${item.id}`}
        title={item.state === "done" ? t("batch.openTitle", { path: item.videoPath }) : item.videoPath}
        disabled={item.state !== "done"}
        onClick={onOpen}
      >
        <b>{baseName(item.videoPath)}</b>
      </button>
      <span className="batch-lang" data-testid={`qlang-${item.id}`}>
        {item.sourceLang !== DEFAULT_SOURCE && (
          <span className="chip-src" data-testid={`qsrc-${item.id}`} title={t("import.source")}>
            {sourceTag(item.sourceLang, t)}
          </span>
        )}
        {langName(item.lang, languages, locale)}
        {isExperimental(item.lang, languages) && <span className="chip-exp">{t("targets.experimental")}</span>}
      </span>
      <span className="batch-status">
        <span className="batch-state" data-testid={`qstate-${item.id}`} data-state={item.state}>
          {t(STATE_LABEL[item.state])}
        </span>
        <span className="batch-step" data-testid={`qstep-${item.id}`}>
          {detail}
        </span>
      </span>
      <span className="batch-prog">
        {(item.state === "running" || item.state === "done") && (
          <>
            <span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
              <span className="bar-fill" style={{ width: `${percent}%` }} />
            </span>
            <span className="percent" data-testid={`qpercent-${item.id}`}>
              {percent}%
            </span>
          </>
        )}
      </span>
      <span className="batch-eta-item" data-testid={`qeta-${item.id}`}>
        {item.etaS !== null ? formatEta(item.etaS, t) : ""}
      </span>
      <span className="batch-actions">
        {actionsFor(item.state).map((a) => {
          const label = t(ACTION[a].label);
          const Icon = ACTION[a].icon;
          return (
            <button
              key={a}
              type="button"
              className="ghost icon-button"
              title={label}
              aria-label={label}
              data-testid={`q${a}-${item.id}`}
              onClick={() => onAct(a)}
            >
              <Icon className="icon" aria-hidden />
            </button>
          );
        })}
      </span>
      {item.error && (
        <p className="batch-error" role="alert" data-testid={`qerror-${item.id}`}>
          <TriangleAlert className="icon" aria-hidden />
          <span>
            <LinkedText text={item.error} />
          </span>
        </p>
      )}
    </li>
  );
}

const ON_DONE_LABEL: Record<OnDone, PlainKey> = { notify: "batch.onDone.notify", sleep: "batch.onDone.sleep", shutdown: "batch.onDone.shutdown" };

/** The safety text of each power action: that it is armed, the warning, what happens, and the consent. */
const POWER_TEXT: Record<PowerAction, { readonly armed: PlainKey; readonly head: PlainKey; readonly body: PlainKey; readonly agree: PlainKey }> = {
  sleep: { armed: "batch.armed.sleep", head: "batch.warn.sleep.head", body: "batch.warn.sleep.body", agree: "batch.agree.sleep" },
  shutdown: { armed: "batch.armed.shutdown", head: "batch.warn.shutdown.head", body: "batch.warn.shutdown.body", agree: "batch.agree.shutdown" },
};
const ON_DONE_KEYS: readonly OnDone[] = ["notify", "sleep", "shutdown"];

function OnDoneSetting({ backend, batch, onError }: { backend: Backend; batch: Batch; onError: (m: string) => void }) {
  const { t } = useT();
  const [pending, setPending] = useState<PowerAction | null>(null);
  const [agree, setAgree] = useState(false);
  const save = (onDone: OnDone, allowPower: boolean) =>
    void putSettings(backend, { onDone, allowPower })
      .catch((e: unknown) => onError(message(e)))
      .finally(() => {
        setPending(null);
        setAgree(false);
      });
  const current = batch.settings;
  const armed = current.onDone !== "notify" && current.allowPower ? current.onDone : null;
  return (
    <div className="ondone" data-testid="ondone">
      <label>
        <span className="ondone-label">
          <Power className="icon" aria-hidden />
          {t("batch.onDone.label")}
        </span>
        <select
          className="lang-select"
          data-testid="ondone-select"
          value={pending ?? current.onDone}
          onChange={(e) => {
            const next = ON_DONE_KEYS.find((k) => k === e.target.value) ?? "notify";
            setAgree(false);
            if (next === "notify") {
              setPending(null);
              save("notify", false);
            } else setPending(next);
          }}
        >
          {ON_DONE_KEYS.map((k) => (
            <option key={k} value={k}>
              {t(ON_DONE_LABEL[k])}
            </option>
          ))}
        </select>
      </label>
      {armed && !pending && (
        <p className="ondone-armed" data-testid="ondone-armed">
          <Moon className="icon" aria-hidden />
          {t(POWER_TEXT[armed].armed)}
        </p>
      )}
      {pending && (
        <div className="ondone-warn" role="alert" data-testid="ondone-warn">
          <p>
            <TriangleAlert className="icon" aria-hidden />
            <b>{t(POWER_TEXT[pending].head)}</b>
            {t(POWER_TEXT[pending].body)}
          </p>
          <label className="ondone-agree">
            <input type="checkbox" data-testid="ondone-agree" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            {t(POWER_TEXT[pending].agree)}
          </label>
          <div className="ondone-buttons">
            <button type="button" className="ghost" onClick={() => setPending(null)}>
              {t("common.cancel")}
            </button>
            <button type="button" className="primary" data-testid="ondone-confirm" disabled={!agree} onClick={() => save(pending, true)}>
              {t("batch.enable")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
