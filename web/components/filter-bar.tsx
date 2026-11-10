"use client";
/* eslint-disable @next/next/no-html-link-for-pages -- same-page navigation uses full page loads on purpose (see lib/navigate.ts) */

import { useEffect, useRef, type ChangeEvent, type FormEvent } from "react";

import { SearchIcon } from "./icons";
import { buttonClass, cx } from "./ui";
import { KIND_OPTIONS } from "@/lib/format";
import { goTo } from "@/lib/navigate";
import { hasFilters, type DashboardFilters } from "@/lib/params";
import type { Category, Company } from "@/lib/types";

const FILTER_KEYS = ["q", "category", "company", "kind", "from", "to"] as const;
const selectClass =
  "h-10 w-full rounded-control border border-line bg-surface px-2.5 text-sm text-ink hover:border-line-strong focus:border-accent md:h-9";

/** Turn the form's fields into a dashboard URL: empty fields are dropped, page resets to 1. */
export function filtersToHref(data: FormData): string {
  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = String(data.get(key) ?? "").trim();
    if (value) params.set(key, value);
  }
  const text = params.toString();
  return text ? `/?${text}` : "/";
}

/**
 * A plain GET form. Pressing Enter in the search box, or changing any control, loads the
 * dashboard with all current filters in the URL. It also works without JavaScript.
 */
export function FilterBar({
  filters,
  categories,
  companies,
  total,
}: {
  filters: DashboardFilters;
  categories: Category[];
  companies: Pick<Company, "slug" | "name">[];
  total: number | null;
}) {
  const searchRef = useRef<HTMLInputElement>(null);
  const active = hasFilters(filters);

  // "/" focuses search, like most developer tools.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
      if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    goTo(filtersToHref(new FormData(event.currentTarget)));
  }

  function changed(event: ChangeEvent<HTMLSelectElement | HTMLInputElement>) {
    event.currentTarget.form?.requestSubmit();
  }

  return (
    <form
      method="get"
      action="/"
      autoComplete="off"
      role="search"
      aria-label="Filter announcements"
      onSubmit={submit}
      className="space-y-3"
    >
      <div className="relative max-w-xl">
        <SearchIcon
          width={17}
          height={17}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
        />
        <input
          ref={searchRef}
          type="search"
          name="q"
          defaultValue={filters.q}
          placeholder="Search, then press Enter"
          aria-label="Search announcements"
          maxLength={100}
          autoComplete="off"
          enterKeyHint="search"
          className="h-11 w-full rounded-control border border-line bg-surface pl-10 pr-10 text-base text-ink placeholder:text-faint hover:border-line-strong focus:border-accent"
        />
        {/* A submit button makes Enter work in browsers when a form has several fields. */}
        <button type="submit" className="sr-only">
          Search
        </button>
        <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-line px-1.5 text-xs text-faint sm:block">
          /
        </kbd>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-5">
        <label className="block text-xs text-muted">
          Category
          <select
            name="category"
            aria-label="Category"
            defaultValue={filters.category}
            onChange={changed}
            className={cx(selectClass, "mt-1")}
          >
            <option value="">All categories</option>
            {categories.map((parent) => (
              <optgroup key={parent.slug} label={parent.name}>
                <option value={parent.slug}>All {parent.name}</option>
                {parent.children.map((child) => (
                  <option key={child.slug} value={child.slug}>
                    {child.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="block text-xs text-muted">
          Company
          <select
            name="company"
            aria-label="Company"
            defaultValue={filters.company}
            onChange={changed}
            className={cx(selectClass, "mt-1")}
          >
            <option value="">All companies</option>
            {companies.map((company) => (
              <option key={company.slug} value={company.slug}>
                {company.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-muted">
          Kind
          <select
            name="kind"
            aria-label="Kind"
            defaultValue={filters.kind}
            onChange={changed}
            className={cx(selectClass, "mt-1")}
          >
            <option value="">All kinds</option>
            {KIND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-muted">
          Published from
          <input
            type="date"
            name="from"
            aria-label="Published from"
            defaultValue={filters.from}
            max={filters.to || undefined}
            onChange={changed}
            className={cx(selectClass, "mt-1")}
          />
        </label>
        <label className="block text-xs text-muted">
          Published to
          <input
            type="date"
            name="to"
            aria-label="Published to"
            defaultValue={filters.to}
            min={filters.from || undefined}
            onChange={changed}
            className={cx(selectClass, "mt-1")}
          />
        </label>
      </div>

      <div
        className="flex min-h-9 flex-wrap items-center gap-3 text-sm text-muted"
        aria-live="polite"
      >
        <span>
          {total === null
            ? ""
            : `${new Intl.NumberFormat("en-GB").format(total)} ${total === 1 ? "announcement" : "announcements"}${
                active ? " match" : ""
              }`}
        </span>
        {active ? (
          <a href="/" className={buttonClass("ghost", "h-8 px-2")}>
            Clear filters
          </a>
        ) : null}
      </div>
    </form>
  );
}
