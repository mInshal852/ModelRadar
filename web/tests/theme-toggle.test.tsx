import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ThemeToggle,
  THEME_STORAGE_KEY,
  applyTheme,
  readPreference,
  resolveTheme,
} from "@/components/theme-toggle";

function mockSystem(light: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: light && query.includes("light"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => vi.restoreAllMocks());

describe("resolveTheme", () => {
  it("defaults to dark and follows the system only when asked", () => {
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("light", false)).toBe("light");
    expect(resolveTheme("system", true)).toBe("light");
    expect(resolveTheme("system", false)).toBe("dark");
  });
});

describe("ThemeToggle", () => {
  it("is dark by default with three options and the dark one selected", () => {
    mockSystem(false);
    render(<ThemeToggle />);
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Dark theme" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("switches to light, applies it to the page and stores it only in localStorage", async () => {
    mockSystem(false);
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("radio", { name: "Light theme" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(document.cookie).toBe("");
  });

  it("follows the system theme when chosen", async () => {
    mockSystem(true);
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Match system theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.themePref).toBe("system");
  });

  it("restores the stored preference on load", () => {
    mockSystem(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(<ThemeToggle />);
    expect(screen.getByRole("radio", { name: "Light theme" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("falls back to dark when the stored value is invalid", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(readPreference()).toBe("dark");
  });

  it("still works when storage is unavailable", async () => {
    mockSystem(false);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(readPreference()).toBe("dark");
  });

  it("applyTheme sets both the theme and the preference", () => {
    mockSystem(false);
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.themePref).toBe("light");
  });
});
