export interface SseMessage {
  readonly id: string | null;
  readonly event: string;
  readonly data: string;
}

/**
 * Splits the text received so far into complete server-sent messages and the unfinished rest.
 * Comment lines (keepalives) and messages with no data are dropped.
 */
export function parseSse(buffer: string): { readonly messages: SseMessage[]; readonly rest: string } {
  const text = buffer.replace(/\r\n?/g, "\n");
  const blocks = text.split("\n\n");
  const rest = blocks.pop() ?? "";
  const messages: SseMessage[] = [];
  for (const block of blocks) {
    let id: string | null = null;
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line === "" || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "id") id = value;
      else if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length > 0) messages.push({ id, event, data: data.join("\n") });
  }
  return { messages, rest };
}
