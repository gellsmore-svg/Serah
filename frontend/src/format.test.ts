import { describe, expect, it } from "vitest";
import { formatDay, formatIntensity } from "./format";

describe("display formatting", () => {
  it("rounds derived intensity for display and leaves storage precision alone", () => {
    expect(formatIntensity(72.4)).toBe("72");
    expect(formatIntensity(null)).toBe("–");
  });

  it("formats a UTC day without shifting the calendar date", () => {
    expect(formatDay("2024-03-03")).toBe("3 March 2024");
    expect(formatDay("2024-03-03T23:30:00+00:00")).toBe("3 March 2024");
  });
});
