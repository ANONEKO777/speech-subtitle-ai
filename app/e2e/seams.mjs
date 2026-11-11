// Variables that make the shell record "open this" instead of doing it. Every launch gets them, so
// no driver can start a real browser or Explorer window.
import { join } from "node:path";

/** Defaults for the two open seams, inside `shots`; a value already in `env` wins. */
export function openSeams(shots, env) {
  return {
    VST_OPEN_URL_LOG: env.VST_OPEN_URL_LOG ?? join(shots, "open-url.log"),
    VST_OPEN_FOLDER_LOG: env.VST_OPEN_FOLDER_LOG ?? join(shots, "open-folder.log"),
  };
}
