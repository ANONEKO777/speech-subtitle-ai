import { describe, expect, it } from "vitest";
import { type Available, DAY_MS, DEFAULT_PREFS, due, parsePrefs, planStart } from "./updatePrefs";

const NEWER: Available = { state: "available", current: "0.1.0", version: "0.2.0", notes: "Faster export" };
const HERE = { supported: true, current: "0.1.0" };
const NOW = Date.UTC(2026, 10, 27, 12);

describe("the once-a-day rule", () => {
  it("checks the first time, then not again for a day", () => {
    expect(due(null, NOW)).toBe(true);
    expect(due(NOW - DAY_MS + 1, NOW)).toBe(false);
    expect(due(NOW - DAY_MS, NOW)).toBe(true);
  });

  it("checks when the clock went back past the last check", () => {
    expect(due(NOW + 60_000, NOW)).toBe(true);
  });
});

describe("what the start of the app does", () => {
  it("checks by default", () => {
    expect(planStart(DEFAULT_PREFS, HERE, NOW)).toEqual({ kind: "check" });
  });

  it("does nothing when the person turned it off, even with a version found before", () => {
    expect(planStart({ ...DEFAULT_PREFS, checkAtStart: false, found: NEWER, lastCheckAt: NOW - 1000 }, HERE, NOW)).toEqual({ kind: "nothing" });
    expect(planStart({ ...DEFAULT_PREFS, checkAtStart: false }, HERE, NOW)).toEqual({ kind: "nothing" });
  });

  it("does nothing where this build cannot update itself", () => {
    expect(planStart(DEFAULT_PREFS, { supported: false, current: "0.1.0" }, NOW)).toEqual({ kind: "nothing" });
  });

  it("offers the version found earlier the same day without going online", () => {
    expect(planStart({ ...DEFAULT_PREFS, lastCheckAt: NOW - 1000, found: NEWER }, HERE, NOW)).toEqual({ kind: "offer", update: NEWER });
  });

  it("does not offer a skipped version again", () => {
    expect(planStart({ ...DEFAULT_PREFS, lastCheckAt: NOW - 1000, found: NEWER, skipped: "0.2.0" }, HERE, NOW)).toEqual({ kind: "nothing" });
  });

  it("forgets a version found for another build, as after the update itself", () => {
    expect(planStart({ ...DEFAULT_PREFS, lastCheckAt: NOW - 1000, found: NEWER }, { supported: true, current: "0.2.0" }, NOW)).toEqual({ kind: "nothing" });
  });
});

describe("parsePrefs", () => {
  it("gives the defaults for nothing stored, damage, or a value of another shape", () => {
    for (const raw of [null, "", "{", "[]", "42", '"x"']) expect(parsePrefs(raw)).toEqual(DEFAULT_PREFS);
  });

  it("reads back what it wrote", () => {
    const prefs = {
      checkAtStart: false,
      lastCheckAt: NOW,
      lastFailure: { at: NOW, reason: { text: "x", notices: [{ code: "shell.update.timeout", params: {}, message: "x" }] } },
      skipped: "0.3.0",
      found: NEWER,
    };
    expect(parsePrefs(JSON.stringify(prefs))).toEqual(prefs);
  });

  it("keeps each good field and drops each bad one, so a later build's store still reads", () => {
    const raw = JSON.stringify({ checkAtStart: "yes", lastCheckAt: -5, skipped: 3, found: { version: "0.2.0" }, lastFailure: { at: NOW, reason: 7 }, futureKey: { a: 1 } });
    expect(parsePrefs(raw)).toEqual({ ...DEFAULT_PREFS, lastFailure: { at: NOW, reason: null } });
  });
});
