/** The part of Markdown that `summary.md` uses: headings, a quote, bullet lists, bold and `[mm:ss](#t=sec)` links. */
export type Inline =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "bold"; readonly text: string }
  | { readonly kind: "time"; readonly label: string; readonly seconds: number };

export type Block =
  | { readonly kind: "heading"; readonly level: 1 | 2 | 3; readonly text: Inline[] }
  | { readonly kind: "quote"; readonly text: Inline[] }
  | { readonly kind: "list"; readonly items: Inline[][] }
  | { readonly kind: "paragraph"; readonly text: Inline[] };

const INLINE = /\*\*(.+?)\*\*|\[([^\]]+)\]\(#t=(\d+(?:\.\d+)?)\)/g;

export function parseInline(line: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of line.matchAll(INLINE)) {
    if (m.index > last) out.push({ kind: "text", text: line.slice(last, m.index) });
    if (m[1] !== undefined) out.push({ kind: "bold", text: m[1] });
    else out.push({ kind: "time", label: m[2] ?? "", seconds: Number(m[3]) });
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ kind: "text", text: line.slice(last) });
  return out;
}

export function parseSummary(markdown: string): Block[] {
  const blocks: Block[] = [];
  let list: Inline[][] | null = null;
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim();
    const item = /^[-*]\s+(.*)$/.exec(line);
    if (item) {
      if (!list) {
        list = [];
        blocks.push({ kind: "list", items: list });
      }
      list.push(parseInline(item[1] ?? ""));
      continue;
    }
    list = null;
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = (heading[1] ?? "#").length as 1 | 2 | 3;
      blocks.push({ kind: "heading", level, text: parseInline(heading[2] ?? "") });
    } else if (line.startsWith(">")) {
      blocks.push({ kind: "quote", text: parseInline(line.replace(/^>\s?/, "")) });
    } else if (line !== "") {
      blocks.push({ kind: "paragraph", text: parseInline(line) });
    }
  }
  return blocks;
}
