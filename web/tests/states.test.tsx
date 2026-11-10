import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, ErrorState, KindBadge, Monogram, Skeleton } from "@/components/ui";
import { StatusBadge, statusInfo } from "@/components/source-status";

describe("states", () => {
  it("EmptyState is announced politely and explains what to do", () => {
    render(<EmptyState title="No announcements collected yet">Check the Sources page.</EmptyState>);
    expect(screen.getByRole("status")).toHaveTextContent("No announcements collected yet");
    expect(screen.getByText("Check the Sources page.")).toBeInTheDocument();
  });

  it("ErrorState is an alert with a retry link and no technical detail by default", () => {
    render(<ErrorState retryHref="/sources" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/sources");
    expect(screen.getByRole("alert").textContent).not.toMatch(/stack|exception|sql/i);
  });

  it("Skeleton is hidden from assistive technology", () => {
    const { container } = render(<Skeleton className="h-4" />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("Monogram uses text initials, never an image", () => {
    const { container } = render(<Monogram name="Allen Institute for AI" />);
    expect(container).toHaveTextContent("AI");
    expect(container.querySelector("img")).toBeNull();
  });

  it("KindBadge labels every kind", () => {
    render(<KindBadge kind="model_release" />);
    expect(screen.getByText("Model release")).toBeInTheDocument();
  });
});

describe("source status", () => {
  it.each([
    [{ enabled: true, status: "ok" }, "Healthy"],
    [{ enabled: true, status: "degraded" }, "Degraded"],
    [{ enabled: true, status: "failing" }, "Failing"],
    [{ enabled: true, status: null }, "Not synced yet"],
    [{ enabled: false, status: "disabled" }, "Disabled"],
  ])("%j -> %s", (source, label) => {
    expect(statusInfo(source).label).toBe(label);
    render(<StatusBadge source={source} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
