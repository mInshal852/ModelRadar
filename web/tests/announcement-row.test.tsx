import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnnouncementRow } from "@/components/announcement-row";
import { Feed, groupByDay } from "@/components/feed";
import { makeAnnouncement } from "./fixtures";

describe("AnnouncementRow", () => {
  it("shows the exact title and links to the original official URL", () => {
    render(<AnnouncementRow item={makeAnnouncement({ title: "  GPT‑X: Exact  Title  " })} />);
    const link = screen.getByRole("link", { name: /GPT‑X: Exact\s+Title/ });
    expect(link).toHaveAttribute("href", "https://example.test/posts/test-model-1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("shows company, domain, kind and the source description", () => {
    render(<AnnouncementRow item={makeAnnouncement()} />);
    expect(screen.getByText("Example Labs")).toBeInTheDocument();
    expect(screen.getByText("example.test")).toBeInTheDocument();
    expect(screen.getByText("Unclassified")).toBeInTheDocument();
    expect(screen.getByText("A description from the source.")).toBeInTheDocument();
  });

  it("renders nothing for a missing description instead of inventing text", () => {
    const { container } = render(
      <AnnouncementRow item={makeAnnouncement({ description: null })} />,
    );
    expect(container.querySelector("p")).toBeNull();
  });

  it("shows 'Date not stated' for a missing publication date", () => {
    render(
      <AnnouncementRow
        item={makeAnnouncement({ published_at: null, published_precision: null })}
      />,
    );
    expect(screen.getByText("Date not stated")).toBeInTheDocument();
    expect(document.querySelector("time")).toBeNull();
  });

  it("shows the stated time for datetime precision and none for date-only", () => {
    const { rerender } = render(<AnnouncementRow item={makeAnnouncement()} />);
    expect(screen.getByText(/9 Nov 2026 19:00 UTC/)).toBeInTheDocument();
    rerender(
      <AnnouncementRow
        item={makeAnnouncement({
          published_at: "2026-11-09T00:00:00Z",
          published_precision: "day",
        })}
      />,
    );
    const time = document.querySelector("time");
    expect(time).toHaveTextContent("9 Nov 2026");
    expect(time).not.toHaveTextContent("UTC");
  });

  it("shows model chips only when model data exists", () => {
    const { rerender } = render(<AnnouncementRow item={makeAnnouncement()} />);
    expect(screen.queryByText("Test Model 1")).toBeNull();
    rerender(<AnnouncementRow item={makeAnnouncement({ models: ["Test Model 1"] })} />);
    expect(screen.getByText("Test Model 1")).toBeInTheDocument();
  });

  it("links category chips to the filtered dashboard", () => {
    render(<AnnouncementRow item={makeAnnouncement()} />);
    expect(screen.getByRole("link", { name: "Language and Reasoning" })).toHaveAttribute(
      "href",
      "/?category=language-reasoning",
    );
  });

  it("does not expose any discovery time", () => {
    const { container } = render(<AnnouncementRow item={makeAnnouncement()} />);
    expect(container.textContent).not.toMatch(/first seen|discovered/i);
  });
});

describe("Feed grouping", () => {
  const a = makeAnnouncement({ id: 1, published_at: "2026-11-09T19:00:00Z" });
  const b = makeAnnouncement({ id: 2, published_at: "2026-11-09T08:00:00Z" });
  const c = makeAnnouncement({ id: 3, published_at: "2026-11-05T10:00:00Z" });
  const undated = makeAnnouncement({ id: 4, published_at: null, published_precision: null });

  it("groups by original publication day with undated announcements last", () => {
    const groups = groupByDay([a, b, c, undated]);
    expect(groups.map((g) => g.key)).toEqual(["2026-11-09", "2026-11-05", "undated"]);
    expect(groups[0]?.items).toHaveLength(2);
    expect(groups[2]?.label).toBe("Date not stated");
  });

  it("renders a labelled section per day", () => {
    render(<Feed items={[a, b, undated]} />);
    const sections = screen.getAllByRole("region");
    expect(sections).toHaveLength(2);
    expect(within(sections[0] as HTMLElement).getAllByRole("article")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /^Monday,? 9 November 2026$/ })).toBeInTheDocument();
  });
});
