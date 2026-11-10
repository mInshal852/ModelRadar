import { describe, expect, it } from "vitest";

import {
  formatPublished,
  formatRelative,
  initials,
  isKind,
  KIND_LABELS,
  NO_DATE_LABEL,
  plural,
} from "@/lib/format";

describe("formatPublished", () => {
  it("shows 'Date not stated' for a missing date, never a substitute", () => {
    const result = formatPublished(null, null);
    expect(result).toEqual({ date: NO_DATE_LABEL, time: null, dayKey: null, iso: null });
  });

  it("treats an unparseable date as missing", () => {
    expect(formatPublished("not a date", "day").date).toBe(NO_DATE_LABEL);
  });

  it("shows no time for date-only precision", () => {
    const result = formatPublished("2026-11-06T00:00:00Z", "day");
    expect(result.date).toBe("6 Nov 2026");
    expect(result.time).toBeNull();
  });

  it("does not invent a time for a day-precision value even if it has one", () => {
    expect(formatPublished("2026-11-06T13:30:00Z", "day").time).toBeNull();
  });

  it("shows the stated time in UTC for datetime precision", () => {
    const result = formatPublished("2026-11-09T19:00:00Z", "datetime");
    expect(result.date).toBe("9 Nov 2026");
    expect(result.time).toBe("19:00 UTC");
    expect(result.dayKey).toBe("2026-11-09");
  });

  it("hides a time of exactly 00:00 UTC (how feeds usually write a date)", () => {
    expect(formatPublished("2026-11-09T00:00:00Z", "datetime").time).toBeNull();
  });

  it("converts offsets to UTC before grouping by day", () => {
    expect(formatPublished("2026-11-06T23:30:00-08:00", "datetime").dayKey).toBe("2026-11-07");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-11-10T12:00:00Z");
  it.each([
    ["2026-11-10T11:59:40Z", "just now"],
    ["2026-11-10T11:55:00Z", "5 min ago"],
    ["2026-11-10T09:00:00Z", "3 h ago"],
    ["2026-11-07T12:00:00Z", "3 d ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });
  it("says Never when there is no time", () => {
    expect(formatRelative(null, now)).toBe("Never");
  });
  it("falls back to a date for old times", () => {
    expect(formatRelative("2026-01-02T00:00:00Z", now)).toBe("2 Jan 2026");
  });
});

describe("helpers", () => {
  it("labels unclassified announcements honestly", () => {
    expect(KIND_LABELS.other).toBe("Unclassified");
  });
  it("validates kinds", () => {
    expect(isKind("model_release")).toBe(true);
    expect(isKind("press")).toBe(false);
    expect(isKind(undefined)).toBe(false);
  });
  it("builds monograms from names", () => {
    expect(initials("Google DeepMind")).toBe("GD");
    expect(initials("Pika")).toBe("PI");
    expect(initials("")).toBe("?");
  });
  it("pluralises counts", () => {
    expect(plural(1, "company", "companies")).toBe("1 company");
    expect(plural(1090, "announcement")).toBe("1,090 announcements");
  });
});
