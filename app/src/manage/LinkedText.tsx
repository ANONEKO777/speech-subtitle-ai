import { ExternalLink } from "./ExternalLink";

const URL_IN_TEXT = /(https:\/\/[!-~]*[A-Za-z0-9/_-])/;

/** A message from the backend with each https address in it turned into an `ExternalLink`, so a failure text that names a download page can be clicked. The surrounding text is unchanged. */
export function LinkedText({ text }: { text: string }) {
  return (
    <>
      {text.split(URL_IN_TEXT).map((part, i) =>
        i % 2 === 1 ? (
          <ExternalLink key={i} href={part}>
            {part}
          </ExternalLink>
        ) : (
          part
        ),
      )}
    </>
  );
}
