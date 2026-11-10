import { ChevronLeftIcon, ChevronRightIcon } from "./icons";
import { buttonClass, cx } from "./ui";

export function pageHref(basePath: string, params: Record<string, string>, page: number): string {
  const next = new URLSearchParams(params);
  next.delete("page");
  if (page > 1) next.set("page", String(page));
  const text = next.toString();
  return text ? `${basePath}?${text}` : basePath;
}

/** Page numbers to show: first, last, and a window around the current page. */
export function pageWindow(current: number, pages: number): (number | "gap")[] {
  const keep = new Set([1, pages, current - 1, current, current + 1]);
  const sorted = [...keep].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  sorted.forEach((p, index) => {
    const previous = sorted[index - 1];
    if (previous !== undefined && p - previous > 1) out.push("gap");
    out.push(p);
  });
  return out;
}

export function Pagination({
  basePath = "/",
  params,
  page,
  pages,
}: {
  basePath?: string;
  params: Record<string, string>;
  page: number;
  pages: number;
}) {
  if (pages <= 1) return null;
  const link = (n: number) => pageHref(basePath, params, n);

  return (
    <nav aria-label="Pagination" className="mt-8 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted">
        Page {page} of {pages}
      </p>
      <ul className="flex flex-wrap items-center gap-1">
        <li>
          {page > 1 ? (
            <a href={link(page - 1)} rel="prev" className={buttonClass("secondary")}>
              <ChevronLeftIcon width={16} height={16} />
              Previous
            </a>
          ) : (
            <span aria-disabled="true" className={buttonClass("secondary", "opacity-40")}>
              <ChevronLeftIcon width={16} height={16} />
              Previous
            </span>
          )}
        </li>
        {pageWindow(page, pages).map((entry, index) =>
          entry === "gap" ? (
            <li key={`gap-${index}`} aria-hidden="true" className="px-1 text-faint">
              …
            </li>
          ) : (
            <li key={entry} className="hidden sm:block">
              <a
                href={link(entry)}
                aria-current={entry === page ? "page" : undefined}
                aria-label={`Page ${entry}`}
                className={cx(
                  "inline-flex h-9 min-w-9 items-center justify-center rounded-control px-2 text-sm",
                  entry === page
                    ? "bg-raised font-semibold text-ink"
                    : "text-muted hover:bg-raised",
                )}
              >
                {entry}
              </a>
            </li>
          ),
        )}
        <li>
          {page < pages ? (
            <a href={link(page + 1)} rel="next" className={buttonClass("secondary")}>
              Next
              <ChevronRightIcon width={16} height={16} />
            </a>
          ) : (
            <span aria-disabled="true" className={buttonClass("secondary", "opacity-40")}>
              Next
              <ChevronRightIcon width={16} height={16} />
            </span>
          )}
        </li>
      </ul>
    </nav>
  );
}
