import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Pagination, pageHref, pageWindow } from "@/components/pagination";

describe("pageWindow", () => {
  it("shows every page when there are few", () => {
    expect(pageWindow(2, 3)).toEqual([1, 2, 3]);
  });
  it("collapses distant pages into gaps", () => {
    expect(pageWindow(10, 100)).toEqual([1, "gap", 9, 10, 11, "gap", 100]);
    expect(pageWindow(1, 100)).toEqual([1, 2, "gap", 100]);
    expect(pageWindow(100, 100)).toEqual([1, "gap", 99, 100]);
  });
});

describe("pageHref", () => {
  it("keeps filters, drops page 1 and sets other pages", () => {
    expect(pageHref("/", { q: "gemini", company: "openai" }, 1)).toBe("/?q=gemini&company=openai");
    expect(pageHref("/", { q: "gemini" }, 3)).toBe("/?q=gemini&page=3");
    expect(pageHref("/", {}, 1)).toBe("/");
  });
  it("encodes values", () => {
    expect(pageHref("/", { q: "a b&c" }, 2)).toBe("/?q=a+b%26c&page=2");
  });
});

describe("Pagination", () => {
  it("renders nothing for a single page", () => {
    const { container } = render(<Pagination params={{}} page={1} pages={1} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links to previous and next pages and keeps filters", () => {
    render(<Pagination params={{ company: "openai" }} page={2} pages={5} />);
    expect(screen.getByText("Page 2 of 5")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Previous/ })).toHaveAttribute(
      "href",
      "/?company=openai",
    );
    expect(screen.getByRole("link", { name: /Next/ })).toHaveAttribute(
      "href",
      "/?company=openai&page=3",
    );
    expect(screen.getByRole("link", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  });

  it("disables previous on the first page and next on the last", () => {
    const { rerender } = render(<Pagination params={{}} page={1} pages={3} />);
    expect(screen.queryByRole("link", { name: /Previous/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Next/ })).toBeInTheDocument();
    rerender(<Pagination params={{}} page={3} pages={3} />);
    expect(screen.queryByRole("link", { name: /Next/ })).toBeNull();
  });

  it("is a labelled navigation landmark", () => {
    render(<Pagination params={{}} page={1} pages={2} />);
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
  });
});
