import type { ProjectView } from "./client";
import type { SourceLang } from "./sourceLang";
import { type SourceTargets, targetFor } from "./targets";

/** What an import of a video does, given the project that already stands for it. */
export type ImportPlan =
  /** Open the project, on `prefer` when it has that language. */
  | { readonly kind: "play"; readonly prefer: string | null }
  /** Run the pipeline. `addsTarget` says the speech steps exist already, so only the translation is redone. */
  | { readonly kind: "run"; readonly source: SourceLang; readonly target: string | null; readonly addsTarget: boolean };

interface Known {
  readonly languages: Parameters<typeof targetFor>[0]["languages"];
  readonly targets: SourceTargets;
}

/**
 * A project that is translated and idle is played as it is, unless the person asked for a language it
 * does not have: then the same video is translated again into that language only, in the video
 * language the project was made with. `wanted` is null when the import names no language (a library
 * entry, a queue item), and the project is then played as it stands.
 */
export function planImport(project: ProjectView, chosen: SourceLang | null, wanted: string | null, known: Known): ImportPlan {
  const has = project.translatedLangs;
  const source = has.length > 0 ? project.sourceLang : (chosen ?? project.sourceLang);
  const target = wanted === null ? null : targetFor(known, source, wanted);
  if (project.translated && project.activeJob === null && (target === null || has.includes(target))) {
    return { kind: "play", prefer: target };
  }
  return { kind: "run", source, target, addsTarget: has.length > 0 };
}
