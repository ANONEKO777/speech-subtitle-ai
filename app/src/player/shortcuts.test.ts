import { describe, expect, it } from "vitest";
import { type Action, SHORTCUTS, keyAction } from "./shortcuts";

const press = (key: string, mods: { ctrl?: boolean; shift?: boolean; alt?: boolean; meta?: boolean } = {}) =>
  keyAction({ key, ctrlKey: !!mods.ctrl, shiftKey: !!mods.shift, altKey: !!mods.alt, metaKey: !!mods.meta });

describe("keyAction", () => {
  const table: Array<[string, Action]> = [
    [" ", { kind: "toggle-play" }],
    ["k", { kind: "toggle-play" }],
    ["ArrowLeft", { kind: "seek", seconds: -5 }],
    ["ArrowRight", { kind: "seek", seconds: 5 }],
    ["j", { kind: "seek", seconds: -10 }],
    ["l", { kind: "seek", seconds: 10 }],
    ["ArrowUp", { kind: "volume", delta: 0.05 }],
    ["ArrowDown", { kind: "volume", delta: -0.05 }],
    ["m", { kind: "mute" }],
    ["f", { kind: "fullscreen" }],
    ["s", { kind: "screenshot", invertBurn: false }],
    ["[", { kind: "speed", dir: -1 }],
    ["]", { kind: "speed", dir: 1 }],
    [",", { kind: "frame", dir: -1 }],
    [".", { kind: "frame", dir: 1 }],
    ["a", { kind: "loop" }],
    ["p", { kind: "pip" }],
    ["z", { kind: "offset", deltaMs: -100 }],
    ["x", { kind: "offset", deltaMs: 100 }],
    ["<", { kind: "video", dir: -1 }],
    [">", { kind: "video", dir: 1 }],
    ["?", { kind: "help" }],
    ["0", { kind: "seek-percent", percent: 0 }],
    ["7", { kind: "seek-percent", percent: 70 }],
  ];
  it.each(table)("%s", (key, action) => {
    expect(press(key)).toEqual(action);
  });

  it("answers a capital letter like the small one, and Shift+S inverts the burn choice", () => {
    expect(press("K", { shift: true })).toEqual({ kind: "toggle-play" });
    expect(press("S", { shift: true })).toEqual({ kind: "screenshot", invertBurn: true });
  });

  it("jumps by line with Ctrl and arrows, and leaves other Ctrl, Alt and Meta chords alone", () => {
    expect(press("ArrowLeft", { ctrl: true })).toEqual({ kind: "line", dir: -1 });
    expect(press("ArrowRight", { ctrl: true })).toEqual({ kind: "line", dir: 1 });
    expect(press("z", { ctrl: true })).toBeNull();
    expect(press("s", { ctrl: true })).toBeNull();
    expect(press("f", { alt: true })).toBeNull();
    expect(press("f", { meta: true })).toBeNull();
    expect(press("Tab")).toBeNull();
  });

  it("answers every key the help overlay lists", () => {
    const listed = SHORTCUTS.flatMap((r) => r.keys.split(/\s*[/+]\s*|\s+–\s+/).map((k) => k.trim()));
    const keys = listed.filter((k) => k.length === 1 || /^Arrow|^Space$/.test(k)).map((k) => (k === "Space" ? " " : k));
    expect(keys.length).toBeGreaterThan(15);
    for (const key of keys) {
      const arrow = { "←": "ArrowLeft", "→": "ArrowRight", "↑": "ArrowUp", "↓": "ArrowDown" }[key] ?? key;
      expect(press(arrow) ?? press(arrow, { ctrl: true }) ?? press(arrow, { shift: true }), `key ${key}`).not.toBeNull();
    }
  });
});
