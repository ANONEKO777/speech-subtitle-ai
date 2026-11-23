import { useEffect, useRef } from "react";
import { watchDrops } from "../api/backend";

/**
 * Calls `onDrop` with the paths of files dropped on the window, and `onOver` while a drag is over it.
 * The window listens once while `enabled`. `onDrop` is read at the moment of the drop, so it sees the
 * language the toolbar shows now, and a change of it never leaves an old listener behind.
 */
export function useDrops(enabled: boolean, onDrop: (paths: string[]) => void, onOver: (over: boolean) => void): void {
  const latest = useRef(onDrop);
  useEffect(() => {
    latest.current = onDrop;
  });
  useEffect(() => {
    if (!enabled) return;
    let gone = false;
    let stop: (() => void) | undefined;
    void watchDrops((paths) => latest.current(paths), onOver).then((unlisten) => {
      if (gone) unlisten();
      else stop = unlisten;
    });
    return () => {
      gone = true;
      stop?.();
    };
  }, [enabled, onOver]);
}
