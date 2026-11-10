"use client";
/* eslint-disable @next/next/no-html-link-for-pages -- same-page navigation uses full page loads on purpose (see lib/navigate.ts) */

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { CloseIcon, MenuIcon, RadarMark, SearchIcon } from "./icons";
import { currentSection, NavList } from "./nav";
import { ThemeToggle } from "./theme-toggle";
import { cx } from "./ui";

function Wordmark() {
  return (
    <a href="/" className="flex min-h-11 items-center gap-2.5 rounded-control px-1 text-ink">
      <RadarMark className="text-accent" />
      <span className="text-[17px] font-semibold tracking-tight">ModelRadar</span>
    </a>
  );
}

/** Compact search used on every page except the dashboard, which has its own larger one. */
function QuickSearch() {
  const router = useRouter();
  const [value, setValue] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const q = value.trim();
    router.push(q ? `/?q=${encodeURIComponent(q)}` : "/");
  }

  return (
    <form role="search" onSubmit={submit} className="relative hidden w-full max-w-xs sm:block">
      <SearchIcon
        width={16}
        height={16}
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search announcements"
        aria-label="Search announcements"
        maxLength={100}
        className="h-9 w-full rounded-control border border-line bg-surface pl-8 pr-3 text-sm text-ink placeholder:text-faint hover:border-line-strong focus:border-accent"
      />
    </form>
  );
}

export function AppShell({ footer, children }: { footer: ReactNode; children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const previous = (document.activeElement as HTMLElement | null) ?? menuButton.current;
    drawerRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, [open]);

  const section = currentSection(pathname);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-ink"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-bg px-3 py-4 md:flex">
        <div className="px-1 pb-5">
          <Wordmark />
        </div>
        <NavList />
        <div className="mt-auto px-2 pt-6 text-xs text-muted">{footer}</div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur md:px-8">
          <button
            ref={menuButton}
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
            aria-expanded={open}
            aria-controls="mobile-drawer"
            className="-ml-2 inline-flex h-11 w-11 items-center justify-center rounded-control text-muted hover:bg-raised hover:text-ink md:hidden"
          >
            <MenuIcon />
          </button>
          <span className="text-sm font-medium text-ink md:text-muted">{section}</span>
          <div className="ml-auto flex items-center gap-3">
            {pathname === "/" ? null : <QuickSearch />}
            <ThemeToggle />
          </div>
        </header>

        <main id="content" className="mx-auto w-full max-w-[1080px] px-4 py-8 md:px-8 md:py-10">
          {children}
        </main>
      </div>

      {/* Mobile drawer */}
      {open ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/55"
          />
          <div
            id="mobile-drawer"
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className={cx(
              "absolute inset-y-0 left-0 flex w-[17rem] max-w-[85vw] flex-col border-r border-line bg-bg px-3 py-4 shadow-pop",
            )}
          >
            <div className="flex items-center justify-between px-1 pb-5">
              <Wordmark />
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="inline-flex h-11 w-11 items-center justify-center rounded-control text-muted hover:bg-raised hover:text-ink"
              >
                <CloseIcon />
              </button>
            </div>
            <NavList onNavigate={() => setOpen(false)} />
            <div className="mt-auto px-2 pt-6 text-xs text-muted">{footer}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
