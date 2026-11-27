import { type CSSProperties, useLayoutEffect, useRef, useState } from "react";

/**
 * What stays of a shortened name, and the shortest name that is ever shortened, both in em. The ellipsis takes
 * about one em, so a name only a little longer than what is kept would lose letters and save next to nothing.
 */
const KEPT_EM = 3.5;
const WHOLE_EM = 5;

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
 * it is laid out as plain text. A short name takes its whole width (`.cut-name`), so no rounding can cut it.
 * A longer one is marked as one that may shrink, and CSS then keeps a few characters of it and the words
 * around it, whose width it takes from here.
 */
export function CutName({ name, before = "", after = "", className, tip, onCut }: Props) {
  const box = useRef<HTMLSpanElement>(null);
  const word = useRef<HTMLSpanElement>(null);
  const [fit, setFit] = useState({ shrinks: false, rest: 0, cut: false });

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
      const shrinks = nameWidth > WHOLE_EM * parseFloat(getComputedStyle(outer).fontSize);
      // the browser lays text out in steps of 1/64 px, so a whole name can read a hair wider than its box
      const cut = nameWidth + rest > line.getBoundingClientRect().width + 0.05;
      setFit((was) => (was.shrinks === shrinks && was.rest === rest && was.cut === cut ? was : { shrinks, rest, cut }));
    };
    const watch = new ResizeObserver(measure);
    watch.observe(outer);
    measure();
    return () => watch.disconnect();
  }, [name, before, after]);

  useLayoutEffect(() => onCut?.(fit.cut), [fit.cut, onCut]);

  const widths = { "--name-kept": `${KEPT_EM}em`, "--name-rest": `${fit.rest}px` } as CSSProperties;
  return (
    <span ref={box} className={className ? `cut-name ${className}` : "cut-name"} data-shrinks={fit.shrinks || undefined} data-cut={fit.cut || undefined} style={widths}>
      <span title={tip && fit.cut ? name : undefined}>
        {before}
        <span ref={word}>{name}</span>
        {after}
      </span>
    </span>
  );
}
