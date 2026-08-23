import { describe, expect, it } from "vitest";
import {
  callDurationSeconds,
  formatDate,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
  initials,
  titleCase,
} from "./utils";

describe("formatDate", () => {
  it("returns an em dash for null/undefined/empty", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("returns an em dash for an unparseable date string", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });

  it("formats a real ISO date", () => {
    expect(formatDate("2026-03-15T10:00:00Z")).toContain("2026");
  });
});

describe("formatDateTime", () => {
  it("returns an em dash for null/invalid input", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("garbage")).toBe("—");
  });

  it("formats a real ISO datetime", () => {
    const out = formatDateTime("2026-03-15T10:30:00Z");
    expect(out).toContain("2026");
  });
});

describe("formatRelativeTime", () => {
  it("returns an em dash for null/invalid input", () => {
    expect(formatRelativeTime(null)).toBe("—");
    expect(formatRelativeTime("garbage")).toBe("—");
  });

  it('says "just now" for a timestamp seconds ago', () => {
    const tenSecondsAgo = new Date(Date.now() - 10_000).toISOString();
    expect(formatRelativeTime(tenSecondsAgo)).toBe("just now");
  });

  it("formats minutes ago", () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe("5m ago");
  });

  it("formats hours ago", () => {
    const threeHrAgo = new Date(Date.now() - 3 * 3600_000).toISOString();
    expect(formatRelativeTime(threeHrAgo)).toBe("3h ago");
  });

  it("formats days ago", () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString();
    expect(formatRelativeTime(twoDaysAgo)).toBe("2d ago");
  });
});

describe("formatDuration", () => {
  it("returns an em dash for null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(125)).toBe("2m 5s");
  });

  it("formats zero seconds", () => {
    expect(formatDuration(0)).toBe("0m 0s");
  });
});

describe("callDurationSeconds", () => {
  it("prefers duration_seconds when present", () => {
    const result = callDurationSeconds({
      duration_seconds: 42,
      answered_at: "2026-03-15T10:00:00Z",
      ended_at: "2026-03-15T10:05:00Z",
    });
    expect(result).toBe(42);
  });

  it("derives duration from answered_at/ended_at when duration_seconds is missing", () => {
    const result = callDurationSeconds({
      duration_seconds: null,
      answered_at: "2026-03-15T10:00:00Z",
      ended_at: "2026-03-15T10:01:30Z",
    });
    expect(result).toBe(90);
  });

  it("returns duration_seconds as-is (null) when the call never connected", () => {
    // A call whose SIP leg never connected has no answered_at -- must NOT
    // fall back to started_at-based queue/ring time (see the function's own
    // docstring for why that would be wrong).
    const result = callDurationSeconds({
      duration_seconds: null,
      answered_at: null,
      ended_at: "2026-03-15T10:01:30Z",
    });
    expect(result).toBeNull();
  });

  it("returns duration_seconds as-is when ended_at precedes answered_at (bad data)", () => {
    const result = callDurationSeconds({
      duration_seconds: null,
      answered_at: "2026-03-15T10:05:00Z",
      ended_at: "2026-03-15T10:00:00Z",
    });
    expect(result).toBeNull();
  });
});

describe("initials", () => {
  it("takes the first letter of up to two words", () => {
    expect(initials("Priya Sharma")).toBe("PS");
  });

  it("handles a single word", () => {
    expect(initials("Priya")).toBe("P");
  });

  it("handles extra whitespace", () => {
    expect(initials("  Priya   Sharma  ")).toBe("PS");
  });

  it("ignores a third+ word", () => {
    expect(initials("Priya Kumari Sharma")).toBe("PK");
  });
});

describe("titleCase", () => {
  it("converts snake_case to Title Case", () => {
    expect(titleCase("not_interested")).toBe("Not Interested");
  });

  it("handles a single word", () => {
    expect(titleCase("pending")).toBe("Pending");
  });
});
