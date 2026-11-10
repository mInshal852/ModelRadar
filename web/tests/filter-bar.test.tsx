import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterBar, filtersToHref } from "@/components/filter-bar";
import type { DashboardFilters } from "@/lib/params";
import type { Category } from "@/lib/types";

const goTo = vi.fn();
vi.mock("@/lib/navigate", () => ({ goTo: (href: string) => goTo(href) }));

const NONE: DashboardFilters = {
  q: "",
  category: "",
  company: "",
  kind: "",
  from: "",
  to: "",
  page: 1,
};

const categories: Category[] = [
  {
    slug: "language-reasoning",
    name: "Language and Reasoning",
    description: null,
    announcement_count: 10,
    company_count: 2,
    children: [
      {
        slug: "frontier-llms",
        name: "Frontier LLMs",
        description: null,
        announcement_count: 0,
        company_count: 0,
        children: [],
      },
    ],
  },
];
const companies = [
  { slug: "openai", name: "OpenAI" },
  { slug: "pika", name: "Pika" },
];

function renderBar(filters: Partial<DashboardFilters> = {}, total: number | null = 1090) {
  return render(
    <FilterBar
      filters={{ ...NONE, ...filters }}
      categories={categories}
      companies={companies}
      total={total}
    />,
  );
}

beforeEach(() => goTo.mockReset());

describe("filtersToHref", () => {
  function data(entries: Record<string, string>): FormData {
    const form = new FormData();
    for (const [key, value] of Object.entries(entries)) form.set(key, value);
    return form;
  }
  it("keeps only filled fields, trimmed, and never includes a page", () => {
    expect(filtersToHref(data({ q: " gemini ", category: "", company: "openai", page: "4" }))).toBe(
      "/?q=gemini&company=openai",
    );
  });
  it("returns the plain dashboard when nothing is set", () => {
    expect(filtersToHref(data({ q: "", kind: "" }))).toBe("/");
  });
});

describe("FilterBar", () => {
  it("is a GET form with search, category, company, kind and date range controls", () => {
    renderBar();
    const form = screen.getByRole("search", { name: "Filter announcements" });
    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/");
    expect(screen.getByRole("searchbox", { name: "Search announcements" })).toBeInTheDocument();
    for (const name of ["Category", "Company", "Kind", "Published from", "Published to"]) {
      expect(screen.getByLabelText(name)).toBeInTheDocument();
    }
    expect(screen.getByText("1,090 announcements")).toBeInTheDocument();
  });

  it("shows the filters that are in the URL", () => {
    renderBar({ company: "pika", kind: "other", q: "hello" }, 3);
    expect(screen.getByLabelText("Company")).toHaveValue("pika");
    expect(screen.getByLabelText("Kind")).toHaveValue("other");
    expect(screen.getByRole("searchbox")).toHaveValue("hello");
    expect(screen.getByText("3 announcements match")).toBeInTheDocument();
  });

  it("loads the dashboard with the new company when a select changes", async () => {
    renderBar();
    await userEvent.selectOptions(screen.getByLabelText("Company"), "openai");
    expect(goTo).toHaveBeenCalledWith("/?company=openai");
  });

  it("supports a child category and a kind", async () => {
    renderBar();
    await userEvent.selectOptions(screen.getByLabelText("Category"), "frontier-llms");
    expect(goTo).toHaveBeenLastCalledWith("/?category=frontier-llms");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "research");
    expect(goTo).toHaveBeenLastCalledWith("/?category=frontier-llms&kind=research");
  });

  it("keeps all other filters when one changes, and resets to page 1", async () => {
    renderBar({ q: "gemini", company: "openai", from: "2026-11-01", page: 4 });
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "research");
    expect(goTo).toHaveBeenCalledWith("/?q=gemini&company=openai&kind=research&from=2026-11-01");
  });

  it("searches when Enter is pressed and keeps the active filters", async () => {
    renderBar({ company: "pika" });
    await userEvent.type(screen.getByRole("searchbox"), "new model{Enter}");
    expect(goTo).toHaveBeenCalledWith("/?q=new+model&company=pika");
  });

  it("does not navigate while typing before Enter", async () => {
    renderBar();
    await userEvent.type(screen.getByRole("searchbox"), "abc");
    expect(goTo).not.toHaveBeenCalled();
  });

  it("applies a date range", async () => {
    renderBar();
    await userEvent.type(screen.getByLabelText("Published from"), "2026-11-01");
    expect(goTo).toHaveBeenLastCalledWith("/?from=2026-11-01");
  });

  it("offers a plain 'Clear filters' link only when something is filtered", () => {
    const { unmount } = renderBar();
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
    unmount();
    renderBar({ company: "pika" });
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", "/");
  });

  it("focuses the search box with '/' unless already typing", async () => {
    renderBar();
    await userEvent.keyboard("/");
    expect(screen.getByRole("searchbox", { name: "Search announcements" })).toHaveFocus();
  });

  it("shows no count while it is unknown", () => {
    renderBar({}, null);
    expect(screen.queryByText(/announcements/)).toBeNull();
  });

  it("limits the date range inputs to a valid range", () => {
    renderBar({ from: "2026-11-01", to: "2026-11-09" });
    expect(screen.getByLabelText("Published from")).toHaveAttribute("max", "2026-11-09");
    expect(screen.getByLabelText("Published to")).toHaveAttribute("min", "2026-11-01");
  });
});
