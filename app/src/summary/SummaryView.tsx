import { Fragment } from "react";
import { clock } from "../player/CueList";
import { type Block, type Inline, parseSummary } from "./parse";

function Inlines({ parts, onSeek }: { readonly parts: readonly Inline[]; readonly onSeek: (seconds: number) => void }) {
  return parts.map((part, i) => {
    switch (part.kind) {
      case "bold":
        return <strong key={i}>{part.text}</strong>;
      case "time":
        return (
          <button
            key={i}
            type="button"
            className="chapter-time"
            data-testid="chapter-time"
            data-seconds={part.seconds}
            title={`跳到 ${clock(part.seconds * 1000)}`}
            onClick={() => onSeek(part.seconds)}
          >
            {part.label}
          </button>
        );
      case "text":
        return <Fragment key={i}>{part.text}</Fragment>;
    }
  });
}

function BlockView({ block, onSeek }: { readonly block: Block; readonly onSeek: (seconds: number) => void }) {
  switch (block.kind) {
    case "heading": {
      const Tag = block.level === 1 ? "h2" : "h3";
      return (
        <Tag className={`summary-h${block.level}`}>
          <Inlines parts={block.text} onSeek={onSeek} />
        </Tag>
      );
    }
    case "quote":
      return (
        <blockquote>
          <Inlines parts={block.text} onSeek={onSeek} />
        </blockquote>
      );
    case "list":
      return (
        <ul>
          {block.items.map((item, i) => (
            <li key={i} data-chapter={item[0]?.kind === "time"}>
              <Inlines parts={item} onSeek={onSeek} />
            </li>
          ))}
        </ul>
      );
    case "paragraph":
      return (
        <p>
          <Inlines parts={block.text} onSeek={onSeek} />
        </p>
      );
  }
}

interface Props {
  /** The summary text, null while that language has none. */
  readonly markdown: string | null;
  readonly onSeek: (seconds: number) => void;
}

export function SummaryView({ markdown, onSeek }: Props) {
  if (markdown === null) {
    return (
      <div className="summary-empty" data-testid="summary-empty">
        這個語言還沒有重點摘要。
      </div>
    );
  }
  return (
    <article className="summary" data-testid="summary">
      {parseSummary(markdown).map((block, i) => (
        <BlockView key={i} block={block} onSeek={onSeek} />
      ))}
    </article>
  );
}
