import type { ReactNode } from "react";
import { openUrl } from "./api";

/** An https link that opens in the default browser. The app opens it after the host check in `open_url`, and a refusal is logged, so the window never navigates away or opens the link itself. */
export function ExternalLink({ href, children, testId }: { href: string; children: ReactNode; testId?: string }) {
  return (
    <a
      href={href}
      rel="noreferrer"
      data-testid={testId}
      onClick={(e) => {
        e.preventDefault();
        openUrl(href).catch((err: unknown) => console.error(`cannot open ${href}`, err));
      }}
    >
      {children}
    </a>
  );
}
