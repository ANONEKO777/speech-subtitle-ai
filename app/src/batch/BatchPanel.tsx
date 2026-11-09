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
import { isExperimental, langName } from "./lang";
import {
  type Batch,
  type BatchItem,
  type ItemState,
  type OnDone,
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

const STATE_LABEL: Record<ItemState, string> = {
  queued: "等待中",
  running: "處理中",
  paused: "已暫停",
  done: "完成",
  failed: "失敗",
  cancelled: "已取消",
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
          <span>項已處理</span>
          <span className="batch-eta" data-testid="batch-eta">
            {total.etaS !== null ? `剩餘${formatEta(total.etaS)}` : total.active ? "預估時間：完成第一項後提供" : ""}
          </span>
        </div>
        <div className="batch-tools">
          <button type="button" data-testid="batch-add" onClick={onAdd}>
            <ListPlus className="icon" aria-hidden />
            加入
          </button>
          <button
            type="button"
            data-testid="batch-pause"
            title={batch.paused ? "繼續處理佇列" : "暫停佇列（目前這項會先做完）"}
            onClick={() => run(setQueuePaused(backend, !batch.paused))}
          >
            {batch.paused ? <CirclePlay className="icon" aria-hidden /> : <CirclePause className="icon" aria-hidden />}
            {batch.paused ? "繼續佇列" : "暫停佇列"}
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="batch-clear"
            disabled={!hasFinished}
            onClick={() => run(removeFinished(backend))}
          >
            <Trash2 className="icon" aria-hidden />
            清除已完成
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
          與後端的連線中斷，正在重新連線…（佇列存在磁碟上，不會遺失）
        </p>
      )}
      {batch.paused && (
        <p className="batch-note" data-testid="batch-paused-note">
          佇列已暫停，不會開始新的項目。
        </p>
      )}
      {batch.items.length === 0 ? (
        <p className="batch-empty" data-testid="batch-empty">
          佇列是空的。按「加入」選擇多個影片或一個資料夾，排好之後可以放著讓它跑完。
        </p>
      ) : (
        <ul className="batch-list" ref={list} data-testid="batch-list" data-dragging={drag !== null}>
          {shown.map((id) => {
            const item = byId.get(id);
            if (!item) return null;
            return (
              <Row
                key={id}
                item={item}
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
  readonly languages: readonly LanguageInfo[];
  readonly dragging: boolean;
  readonly canDrag: boolean;
  readonly onOpen: () => void;
  readonly onAct: (a: ItemAction | "remove") => void;
  readonly onDragStart: (e: PointerEvent<HTMLElement>) => void;
  readonly onNudge: (by: -1 | 1) => void;
}

const ACTION = {
  pause: { label: "暫停", icon: CirclePause },
  resume: { label: "繼續", icon: CirclePlay },
  cancel: { label: "取消", icon: X },
  retry: { label: "重試", icon: RotateCcw },
  remove: { label: "移除", icon: Trash2 },
} as const;

function Row({ item, languages, dragging, canDrag, onOpen, onAct, onDragStart, onNudge }: RowProps) {
  const percent = Math.round(item.progress * 100);
  const stepIndex = item.step ? STEP_ORDER.indexOf(item.step) + 1 : 0;
  const detail =
    item.state === "running"
      ? item.step
        ? `${STEP_NAME[item.step]}（${stepIndex}/${STEP_ORDER.length}）`
        : "準備中"
      : item.state === "queued" && item.attempts > 0
        ? "等待續跑"
        : "";
  return (
    <li className="batch-row" data-row-id={item.id} data-testid={`qrow-${item.id}`} data-state={item.state} data-dragging={dragging}>
      <button
        type="button"
        className="ghost icon-button drag-handle"
        data-testid={`qdrag-${item.id}`}
        aria-label="拖曳以重新排序（或按上下鍵）"
        disabled={!canDrag}
        onPointerDown={onDragStart}
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
        title={item.state === "done" ? `${item.videoPath}\n按一下在播放器開啟` : item.videoPath}
        disabled={item.state !== "done"}
        onClick={onOpen}
      >
        <b>{baseName(item.videoPath)}</b>
      </button>
      <span className="batch-lang" data-testid={`qlang-${item.id}`}>
        {langName(item.lang, languages)}
        {isExperimental(item.lang, languages) && <span className="chip-exp">實驗性</span>}
      </span>
      <span className="batch-status">
        <span className="batch-state" data-testid={`qstate-${item.id}`} data-state={item.state}>
          {STATE_LABEL[item.state]}
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
        {item.etaS !== null ? formatEta(item.etaS) : ""}
      </span>
      <span className="batch-actions">
        {actionsFor(item.state).map((a) => {
          const { label, icon: Icon } = ACTION[a];
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
          <span>{item.error}</span>
        </p>
      )}
    </li>
  );
}

const ON_DONE_LABEL: Record<OnDone, string> = { notify: "只通知我（預設）", sleep: "讓電腦睡眠", shutdown: "關機" };
const ON_DONE_KEYS: readonly OnDone[] = ["notify", "sleep", "shutdown"];

function OnDoneSetting({ backend, batch, onError }: { backend: Backend; batch: Batch; onError: (m: string) => void }) {
  const [pending, setPending] = useState<OnDone | null>(null);
  const [agree, setAgree] = useState(false);
  const save = (onDone: OnDone, allowPower: boolean) =>
    void putSettings(backend, { onDone, allowPower })
      .catch((e: unknown) => onError(message(e)))
      .finally(() => {
        setPending(null);
        setAgree(false);
      });
  const current = batch.settings;
  const powered = current.onDone !== "notify" && current.allowPower;
  const word = (a: OnDone) => (a === "sleep" ? "睡眠" : "關機");
  return (
    <div className="ondone" data-testid="ondone">
      <label>
        <span className="ondone-label">
          <Power className="icon" aria-hidden />
          佇列全部完成後
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
              {ON_DONE_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      {powered && !pending && (
        <p className="ondone-armed" data-testid="ondone-armed">
          <Moon className="icon" aria-hidden />
          已啟用：全部完成後會{current.onDone === "sleep" ? "讓電腦睡眠" : "關機"}，之前有 60 秒倒數可以取消。
        </p>
      )}
      {pending && (
        <div className="ondone-warn" role="alert" data-testid="ondone-warn">
          <p>
            <TriangleAlert className="icon" aria-hidden />
            <b>{word(pending)}會中斷電腦上的其他工作。</b>
            佇列跑完後，電腦會先倒數 60 秒，可以按「取消」阻止；沒有取消就會
            {pending === "sleep" ? "進入睡眠，睡眠期間不會有任何處理。" : "關機，未儲存的資料會遺失。"}
          </p>
          <label className="ondone-agree">
            <input type="checkbox" data-testid="ondone-agree" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            我了解，並同意佇列完成後{word(pending)}
          </label>
          <div className="ondone-buttons">
            <button type="button" className="ghost" onClick={() => setPending(null)}>
              取消
            </button>
            <button type="button" className="primary" data-testid="ondone-confirm" disabled={!agree} onClick={() => save(pending, true)}>
              啟用
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
