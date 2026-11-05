import { describe, expect, it } from "vitest";
import { DEFAULTS, parseSettings } from "./settings";

describe("parseSettings", () => {
  it("returns the defaults for nothing or garbage", () => {
    expect(parseSettings(null)).toEqual(DEFAULTS);
    expect(parseSettings("{not json")).toEqual(DEFAULTS);
  });

  it("keeps valid values and repairs invalid ones", () => {
    const s = parseSettings(JSON.stringify({ mode: "zh", fontSize: 500, color: "red", zhFirst: false }));
    expect(s).toMatchObject({ mode: "zh", fontSize: 64, color: DEFAULTS.color, zhFirst: false });
  });
});
