import { describe, expect, it } from "vitest";
import { DEFAULT_PREFS, parsePrefs } from "./prefs";

describe("parsePrefs", () => {
  it("keeps what was saved", () => {
    expect(parsePrefs('{"volume":0.4,"muted":true,"rate":1.5}')).toEqual({ volume: 0.4, muted: true, rate: 1.5 });
  });
  it("repairs a missing, damaged or out-of-range store", () => {
    expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("{oops")).toEqual(DEFAULT_PREFS);
    expect(parsePrefs('{"volume":7,"rate":9}')).toEqual(DEFAULT_PREFS);
  });
});
