import { describe, expect, it } from "vitest";

import { activeParams, hasFilters, readDashboardFilters } from "@/lib/params";

describe("readDashboardFilters", () => {
  it("returns empty defaults", () => {
    const filters = readDashboardFilters({});
    expect(filters).toEqual({
      q: "",
      category: "",
      company: "",
      kind: "",
      from: "",
      to: "",
      page: 1,
    });
    expect(hasFilters(filters)).toBe(false);
  });

  it("reads valid values", () => {
    const filters = readDashboardFilters({
      q: " gemini ",
      category: "language-reasoning",
      company: "openai",
      kind: "model_release",
      from: "2026-11-01",
      to: "2026-11-09",
      page: "3",
    });
    expect(filters.q).toBe("gemini");
    expect(filters.page).toBe(3);
    expect(activeParams(filters)).toEqual({
      q: "gemini",
      category: "language-reasoning",
      company: "openai",
      kind: "model_release",
      from: "2026-11-01",
      to: "2026-11-09",
    });
  });

  it("drops invalid values instead of forwarding them to the API", () => {
    const filters = readDashboardFilters({
      category: "Not A Slug!",
      company: "../etc",
      kind: "press",
      from: "yesterday",
      to: "2026-13-99x",
      page: "-4",
    });
    expect(hasFilters(filters)).toBe(false);
    expect(filters.page).toBe(1);
  });

  it("uses the first value of repeated parameters and caps the query length", () => {
    const filters = readDashboardFilters({ q: ["a", "b"], page: "abc" });
    expect(filters.q).toBe("a");
    expect(filters.page).toBe(1);
    expect(readDashboardFilters({ q: "x".repeat(300) }).q).toHaveLength(100);
  });
});
