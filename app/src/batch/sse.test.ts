import { describe, expect, it } from "vitest";
import { classifyPath } from "./paths";
import { parseSse } from "./sse";

describe("server-sent events", () => {
  it("reads id, event and data from complete messages and keeps the unfinished rest", () => {
    const { messages, rest } = parseSse('id: 3\nevent: item\ndata: {"a":1}\n\nid: 4\nevent: queue\ndata: {"b"');
    expect(messages).toEqual([{ id: "3", event: "item", data: '{"a":1}' }]);
    expect(rest).toBe('id: 4\nevent: queue\ndata: {"b"');
  });

  it("completes a message split across chunks", () => {
    const first = parseSse("id: 1\nevent: done\nda");
    const second = parseSse(first.rest + 'ta: {"x":2}\n\n');
    expect(second.messages).toEqual([{ id: "1", event: "done", data: '{"x":2}' }]);
    expect(second.rest).toBe("");
  });

  it("skips keepalive comments and handles CRLF", () => {
    const { messages } = parseSse(": keepalive\n\nid: 9\r\nevent: order\r\ndata: {}\r\n\r\n");
    expect(messages).toEqual([{ id: "9", event: "order", data: "{}" }]);
  });

  it("joins several data lines", () => {
    expect(parseSse("event: x\ndata: a\ndata: b\n\n").messages[0]?.data).toBe("a\nb");
  });
});

describe("dropped paths", () => {
  it("takes a media extension for a file and anything else for a folder", () => {
    expect(classifyPath("D:\\talks\\one.MP4")).toBe("file");
    expect(classifyPath("D:\\talks\\audio.wav")).toBe("file");
    expect(classifyPath("D:\\talks")).toBe("folder");
    expect(classifyPath("D:\\talks\\notes.txt")).toBe("folder");
  });
});
