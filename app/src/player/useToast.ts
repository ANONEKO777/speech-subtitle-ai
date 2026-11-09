import { useCallback, useEffect, useRef, useState } from "react";

export interface ToastData {
  readonly text: string;
  readonly action?: { readonly label: string; readonly run: () => void };
  /** Marks a failure so the toast looks like one. */
  readonly error?: boolean;
}

/** One message at a time, gone after `ms`. A new message replaces the old one. */
export function useToast(ms = 7000) {
  const [toast, setToast] = useState<ToastData | null>(null);
  const timer = useRef(0);
  const show = useCallback(
    (data: ToastData) => {
      window.clearTimeout(timer.current);
      setToast(data);
      timer.current = window.setTimeout(() => setToast(null), ms);
    },
    [ms],
  );
  const hide = useCallback(() => {
    window.clearTimeout(timer.current);
    setToast(null);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return { toast, show, hide };
}
