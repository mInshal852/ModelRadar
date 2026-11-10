import Link from "next/link";

import { Chip, EmptyState, ErrorState, ExternalLink, Monogram, PageHeader } from "@/components/ui";
import { ExternalIcon } from "@/components/icons";
import { load } from "@/lib/api";
import { formatCount, formatPublished } from "@/lib/format";
import type { Company, Page } from "@/lib/types";

export const metadata = { title: "Companies" };

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default async function CompaniesPage() {
  const { data, error } = await load<Page<Company>>("/v1/companies", { page_size: 100 });

  return (
    <>
      <PageHeader
        title="Companies"
        description="The AI companies whose official sources ModelRadar follows. Open a company to see only its announcements."
      />
      {error ? (
        <ErrorState retryHref="/companies" />
      ) : data.items.length === 0 ? (
        <EmptyState title="No companies configured">
          Companies are loaded from the project configuration.
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.items.map((company) => {
            const latest = formatPublished(company.latest_published_at, "day");
            return (
              <li key={company.slug}>
                <article className="flex h-full flex-col rounded-panel border border-line bg-surface p-4 transition-colors hover:border-line-strong">
                  <div className="flex items-start gap-3">
                    <Monogram name={company.name} size="lg" />
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold tracking-tight text-ink">
                        {company.name}
                      </h2>
                      <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted">
                        <ExternalLink
                          href={company.website_url}
                          className="inline-flex items-center gap-1 hover:text-accent"
                        >
                          {hostname(company.website_url)}
                          <ExternalIcon width={13} height={13} />
                        </ExternalLink>
                        {company.country ? <span>{company.country}</span> : null}
                      </p>
                    </div>
                  </div>
                  {company.description ? (
                    <p className="mt-3 text-muted">{company.description}</p>
                  ) : null}
                  {company.categories.length ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {company.categories.map((category) => (
                        <Chip key={category.slug} href={`/?category=${category.slug}`}>
                          {category.name}
                        </Chip>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-4 text-sm">
                    <span className="text-muted">
                      <span className="font-semibold text-ink">
                        {formatCount(company.announcement_count)}
                      </span>{" "}
                      {company.announcement_count === 1 ? "announcement" : "announcements"}
                      {company.latest_published_at ? (
                        <span className="text-faint"> · latest {latest.date}</span>
                      ) : null}
                    </span>
                    <Link
                      href={`/?company=${company.slug}`}
                      className="font-medium text-accent hover:underline"
                      aria-label={`View announcements from ${company.name}`}
                    >
                      View announcements
                    </Link>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
