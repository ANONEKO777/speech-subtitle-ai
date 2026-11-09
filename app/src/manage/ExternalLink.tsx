import type { ReactNode } from "react";
import { openUrl } from "./api";

/** An https link that opens in the default browser. The app opens it, so the window never navigates away. */
export function ExternalLink({ href, children, testId }: { href: string; children: ReactNode; testId?: string }) {
  return (
    <a
      href={href}
      rel="noreferrer"
      data-testid={testId}
      onClick={(e) => {
        e.preventDefault();
        void openUrl(href).catch(() => window.open(href, "_blank", "noreferrer"));
      }}
    >
      {children}
    </a>
  );
}
