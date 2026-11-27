import { type CSSProperties, useLayoutEffect, useRef, useState } from "react";

interface Props {
  /** The name that gives way. */
  readonly name: string;
  /** The words of the sentence around it, which always stay whole. */
  readonly before?: string;
  readonly after?: string;
  readonly className?: string;
  /** Give the name a tooltip while it is shortened. Leave it out where a control around it already has one that says the name. */
  readonly tip?: boolean;
  readonly onCut?: (cut: boolean) => void;
}

/**
 * A language name that is shortened with an ellipsis when the toolbar has no room for all of it. Until then
 * it is laid out as plain text. CSS keeps a few characters of it on screen (`.cut-name`), and takes two
 * widths from here for that: the whole text's, so that a short name is not padded out, and that of the words
 * around the name.
 */
export function CutName({ name, before = "", after = "", className, tip, onCut }: Props) {
  const box = useRef<HTMLSpanElement>(null);
  const word = useRef<HTMLSpanElement>(null);
  const [fit, setFit] = useState({ full: 0, rest: 0, cut: false });

  useLayoutEffect(() => {
    const outer = box.current;
    const inner = word.current;
    const line = inner?.parentElement;
    if (!outer || !inner || !line || typeof ResizeObserver === "undefined") return;
    // a range over the text reads its whole width, also while the box shows only part of it
    const widthOf = (node: Node) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return range.getBoundingClientRect().width;
    };
    const measure = () => {
      const nameWidth = widthOf(inner);
      const rest = [...line.childNodes].reduce((sum, node) => (node === inner ? sum : sum + widthOf(node)), 0);
      const full = nameWidth + rest;
      const cut = full > line.getBoundingClientRect().width + 0.05;
      setFit((was) => (was.full === full && was.rest === rest && was.cut === cut ? was : { full, rest, cut }));
    };
    const watch = new ResizeObserver(measure);
    watch.observe(outer);
    measure();
    return () => watch.disconnect();
  }, [name, before, after]);

  useLayoutEffect(() => onCut?.(fit.cut), [fit.cut, onCut]);

  const widths = { "--name-full": `${Math.max(0, fit.full - 0.5)}px`, "--name-rest": `${fit.rest}px` } as CSSProperties;
  return (
    <span ref={box} className={className ? `cut-name ${className}` : "cut-name"} data-cut={fit.cut || undefined} style={widths}>
      <span title={tip && fit.cut ? name : undefined}>
        {before}
        <span ref={word}>{name}</span>
        {after}
      </span>
    </span>
  );
}
