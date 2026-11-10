"use client";

import { useEffect, useState } from "react";

import { MoonIcon, SunIcon, SystemIcon } from "./icons";
import { cx } from "./ui";

export type ThemePreference = "dark" | "light" | "system";
export const THEME_STORAGE_KEY = "modelradar-theme";

const OPTIONS: { value: ThemePreference; label: string; icon: typeof SunIcon }[] = [
  { value: "dark", label: "Dark theme", icon: MoonIcon },
  { value: "light", label: "Light theme", icon: SunIcon },
  { value: "system", label: "Match system theme", icon: SystemIcon },
];

export function resolveTheme(pref: ThemePreference, prefersLight: boolean): "dark" | "light" {
  if (pref === "light") return "light";
  if (pref === "system") return prefersLight ? "light" : "dark";
  return "dark";
}

export function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "system" || stored === "dark" ? stored : "dark";
  } catch {
    return "dark"; // storage unavailable (private mode, blocked): fall back to the default
  }
}

export function applyTheme(pref: ThemePreference): void {
  const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)").matches ?? false;
  document.documentElement.dataset.theme = resolveTheme(pref, prefersLight);
  document.documentElement.dataset.themePref = pref;
}

/** The preference lives only in this browser's localStorage; nothing is sent anywhere. */
export function ThemeToggle() {
  const [pref, setPref] = useState<ThemePreference>("dark");

  useEffect(() => {
    setPref(readPreference());
  }, []);

  useEffect(() => {
    if (pref !== "system") return;
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyTheme("system");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [pref]);

  function choose(next: ThemePreference) {
    setPref(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* the choice still applies for this visit */
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="inline-flex rounded-control border border-line bg-surface p-0.5"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={pref === value}
          aria-label={label}
          title={label}
          onClick={() => choose(value)}
          className={cx(
            "inline-flex h-8 w-8 items-center justify-center rounded-[5px] transition-colors",
            pref === value ? "bg-raised text-ink" : "text-faint hover:text-ink",
          )}
        >
          <Icon width={16} height={16} />
        </button>
      ))}
    </div>
  );
}
