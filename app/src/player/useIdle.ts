import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/**
 * The player controls hide after the pointer has rested. They stay while a control inside them has
 * focus (so a person tabbing through them still sees where they are). A mouse click also leaves focus
 * on the button or slider that was pressed, so without the hand-back below the controls would stay
 * on screen for good after the pointer left the window, until the person clicked somewhere else.
 *
 * `wake` is for pointer movement. `idle` turns true `ms` after the last wake, and at that moment a
 * control that holds focus only because of a pointer press gives the focus back. Focus that arrived
 * by Tab is kept.
 */
export function useIdle(stage: RefObject<HTMLElement | null>, ms: number) {
  const [idle, setIdle] = useState(false);
  const timer = useRef(0);
  const tabbed = useRef(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Tab") tabbed.current = true;
    };
    const onPointer = () => {
      tabbed.current = false;
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onPointer, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onPointer, true);
    };
  }, []);

  const wake = useCallback(() => {
    setIdle(false);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const held = document.activeElement;
      const controls = stage.current?.querySelector(".controls");
      if (!tabbed.current && held instanceof HTMLElement && controls?.contains(held)) held.blur();
      setIdle(true);
    }, ms);
  }, [stage, ms]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return { idle, wake };
}
