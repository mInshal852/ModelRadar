import Link from "next/link";

import { ErrorState, EmptyState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { formatCount, plural } from "@/lib/format";
import type { Category } from "@/lib/types";

export const metadata = { title: "Categories" };

export default async function CategoriesPage() {
  const { data, error } = await load<Category[]>("/v1/categories");

  return (
    <>
      <PageHeader
        title="Categories"
        description="The fixed set of AI areas ModelRadar organises announcements by. Until announcements are classified individually, each one takes the categories of the company that published it."
      />
      {error ? (
        <ErrorState retryHref="/categories" />
      ) : data.length === 0 ? (
        <EmptyState title="No categories configured">
          Categories are loaded from the project configuration.
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((category) => (
            <li key={category.slug}>
              <article className="flex h-full flex-col rounded-panel border border-line bg-surface p-4 transition-colors hover:border-line-strong">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">{category.name}</h2>
                  <p className="shrink-0 text-right text-sm text-muted">
                    <span className="text-lg font-semibold text-ink">
                      {formatCount(category.announcement_count)}
                    </span>
                    <span className="block text-xs">
                      {category.announcement_count === 1 ? "announcement" : "announcements"}
                    </span>
                  </p>
                </div>
                {category.description ? (
                  <p className="mt-1 text-muted">{category.description}</p>
                ) : null}
                {category.children.length ? (
                  <p className="mt-2 text-sm text-muted">
                    {category.children.map((child) => child.name).join(", ")}
                  </p>
                ) : null}
                <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-sm">
                  <span className="text-faint">
                    {plural(category.company_count, "company", "companies")}
                  </span>
                  <Link
                    href={`/?category=${category.slug}`}
                    className="font-medium text-accent hover:underline"
                    aria-label={`View announcements in ${category.name}`}
                  >
                    View announcements
                  </Link>
                </div>
              </article>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
