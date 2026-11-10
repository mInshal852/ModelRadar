import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/shell";
import { NAV_ITEMS, currentSection, isActive } from "@/components/nav";

let pathname = "/";
const push = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push, replace: vi.fn() }),
}));

beforeEach(() => {
  pathname = "/";
  push.mockReset();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia;
});

describe("navigation helpers", () => {
  it("lists the six sections in order", () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      "Dashboard",
      "Models",
      "Categories",
      "Companies",
      "Sources",
      "About",
    ]);
  });
  it("matches the active page", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/models", "/")).toBe(false);
    expect(isActive("/sources", "/sources")).toBe(true);
    expect(isActive("/sources/x", "/sources")).toBe(true);
    expect(isActive("/sourcesfoo", "/sources")).toBe(false);
  });
  it("names the current section", () => {
    expect(currentSection("/companies")).toBe("Companies");
    expect(currentSection("/nowhere")).toBe("ModelRadar");
  });
});

describe("AppShell", () => {
  it("renders landmarks, a skip link and the footer", () => {
    render(
      <AppShell footer={<p>1,090 announcements</p>}>
        <h1>Page</h1>
      </AppShell>,
    );
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute(
      "href",
      "#content",
    );
    expect(screen.getByText("1,090 announcements")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("marks the active page", () => {
    pathname = "/models";
    render(
      <AppShell footer={null}>
        <p>x</p>
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Models" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("opens and closes the mobile drawer with the button and Escape", async () => {
    render(
      <AppShell footer={null}>
        <p>x</p>
      </AppShell>,
    );
    const open = screen.getByRole("button", { name: "Open navigation" });
    expect(open).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(open);
    const dialog = screen.getByRole("dialog", { name: "Navigation" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getAllByRole("link").length).toBeGreaterThanOrEqual(6);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes the drawer when a link is chosen", async () => {
    render(
      <AppShell footer={null}>
        <p>x</p>
      </AppShell>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const dialog = screen.getByRole("dialog", { name: "Navigation" });
    await userEvent.click(within(dialog).getByRole("link", { name: "Sources" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers quick search on other pages and sends the query to the dashboard", async () => {
    pathname = "/about";
    render(
      <AppShell footer={null}>
        <p>x</p>
      </AppShell>,
    );
    const box = screen.getByRole("searchbox", { name: "Search announcements" });
    await userEvent.type(box, "gemini{Enter}");
    expect(push).toHaveBeenCalledWith("/?q=gemini");
  });

  it("hides quick search on the dashboard, which has its own", () => {
    pathname = "/";
    render(
      <AppShell footer={null}>
        <p>x</p>
      </AppShell>,
    );
    expect(screen.queryByRole("searchbox")).toBeNull();
  });
});
