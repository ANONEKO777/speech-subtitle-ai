import type { ComponentProps } from "react";
import { SettingsPage } from "./SettingsPage";
import { UpdateSection } from "./UpdateSection";
import { useUpdates } from "./useUpdates";
import type { Work } from "./work";

/** The settings section with its own update state and no check at start, for tests that render it alone. */
export function UpdateSectionAlone({ work = null }: { work?: Work }) {
  return <UpdateSection updates={useUpdates(work)} />;
}

/** The settings page outside the app, with its own update state and no check at start. */
export function SettingsPageAlone(props: Omit<ComponentProps<typeof SettingsPage>, "updates">) {
  return <SettingsPage {...props} updates={useUpdates(null)} />;
}
