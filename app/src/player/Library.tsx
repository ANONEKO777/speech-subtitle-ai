import { Clock, Film, ListPlus, ListX, Play, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Backend } from "../api/client";
import { type LibraryItem, fetchThumbnail } from "../api/library";
import { type Queue } from "./queue";
import { playClock } from "./transport";

interface Props {
  readonly backend: Backend;
  readonly items: readonly LibraryItem[];
  readonly queue: Queue;
  /** The project on screen, if any. */
  readonly currentId: string | null;
  /** Names of language codes, for the chips. */
  readonly names: ReadonlyMap<string, string>;
  readonly onPlay: (item: LibraryItem) => void;
  readonly onEnqueue: (id: string) => void;
  readonly onDequeue: (id: string) => void;
  readonly onQueueAll: () => void;
}

/** A thumbnail made on first sight: the backend cuts it with ffmpeg, so only items on screen ask. */
function Thumb({ backend, id }: { backend: Backend; id: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    const node = box.current;
    if (!node) return;
    let url: string | null = null;
    let alive = true;
    const watch = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      watch.disconnect();
      void fetchThumbnail(backend, id)
        .then((u) => {
          if (alive) setSrc((url = u));
          else if (u) URL.revokeObjectURL(u);
        })
        .catch(() => undefined);
    });
    watch.observe(node);
    return () => {
      alive = false;
      watch.disconnect();
      if (url) URL.revokeObjectURL(url);
    };
  }, [backend, id]);
  return (
    <div className="thumb" ref={box}>
      {src ? <img src={src} alt="" /> : <Film className="icon" aria-hidden />}
    </div>
  );
}

function Card({ item, p, queued, kind }: { item: LibraryItem; p: Props; queued: boolean; kind: "recent" | "lib" }) {
  const resume = item.positionS > 5 && item.positionS < item.durationS - 10;
  return (
    <li className="lib-card" data-testid={`${kind}-${item.id}`} data-current={item.id === p.currentId} data-missing={!item.exists}>
      <button type="button" className="lib-open" data-testid={`${kind}-play-${item.id}`} disabled={!item.exists} onClick={() => p.onPlay(item)}>
        <Thumb backend={p.backend} id={item.id} />
        <span className="lib-meta">
          <span className="lib-title" title={item.title}>
            {item.title}
          </span>
          <span className="lib-sub">
            <span className="num">{item.durationS > 0 ? playClock(item.durationS) : "—"}</span>
            {item.langs.map((l) => (
              <span key={l} className="chip">
                {p.names.get(l) ?? l}
              </span>
            ))}
            {!item.exists && (
              <span className="lib-missing">
                <TriangleAlert className="icon" aria-hidden />
                找不到影片檔
              </span>
            )}
          </span>
          {resume && (
            <span className="lib-progress" title={`上次看到 ${playClock(item.positionS)}`}>
              <span style={{ width: `${(item.positionS / item.durationS) * 100}%` }} />
            </span>
          )}
        </span>
        <Play className="icon lib-play" aria-hidden />
      </button>
      <button
        type="button"
        className="ghost icon-button"
        data-testid={`${kind}-queue-${item.id}`}
        title={queued ? "移出播放佇列" : "加入播放佇列"}
        aria-label={queued ? "移出播放佇列" : "加入播放佇列"}
        aria-pressed={queued}
        onClick={() => (queued ? p.onDequeue(item.id) : p.onEnqueue(item.id))}
      >
        {queued ? <ListX className="icon" aria-hidden /> : <ListPlus className="icon" aria-hidden />}
      </button>
    </li>
  );
}

export function Library(p: Props) {
  const recent = [...p.items].filter((i) => i.openedAtMs > 0).slice(0, 4);
  const byId = new Map(p.items.map((i) => [i.id, i]));
  const queued = new Set(p.queue.ids);
  if (p.items.length === 0) {
    return (
      <p className="side-empty" data-testid="library-empty">
        還沒有處理完成的影片。匯入並處理一部影片後，會出現在這裡。
      </p>
    );
  }
  return (
    <div className="library" data-testid="library">
      {p.queue.ids.length > 0 && (
        <section aria-label="播放佇列">
          <h3>播放佇列</h3>
          <ol className="queue" data-testid="queue-list">
            {p.queue.ids.map((id, i) => {
              const item = byId.get(id);
              return (
                <li key={id} data-testid={`queue-item-${i + 1}`} data-current={id === p.queue.current}>
                  <button type="button" className="queue-open" disabled={!item?.exists} onClick={() => item && p.onPlay(item)}>
                    <span className="num">{i + 1}</span>
                    <span className="lib-title">{item?.title ?? id}</span>
                  </button>
                  <button type="button" className="ghost icon-button" aria-label="移出播放佇列" onClick={() => p.onDequeue(id)}>
                    <ListX className="icon" aria-hidden />
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      )}
      {recent.length > 0 && (
        <section aria-label="最近開啟">
          <h3>
            <Clock className="icon" aria-hidden />
            最近開啟
          </h3>
          <ul className="lib-grid" data-testid="recent-list">
            {recent.map((item) => (
              <Card key={item.id} item={item} p={p} queued={queued.has(item.id)} kind="recent" />
            ))}
          </ul>
        </section>
      )}
      <section aria-label="所有影片">
        <h3>
          所有影片
          <button type="button" className="ghost" data-testid="queue-all" onClick={p.onQueueAll}>
            <ListPlus className="icon" aria-hidden />
            全部加入佇列
          </button>
        </h3>
        <ul className="lib-grid" data-testid="library-list">
          {p.items.map((item) => (
            <Card key={item.id} item={item} p={p} queued={queued.has(item.id)} kind="lib" />
          ))}
        </ul>
      </section>
    </div>
  );
}
