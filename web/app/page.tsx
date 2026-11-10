/* eslint-disable @next/next/no-html-link-for-pages -- same-page navigation uses full page loads on purpose (see lib/navigate.ts) */
import { FilterBar } from "@/components/filter-bar";
import { Feed } from "@/components/feed";
import { Pagination } from "@/components/pagination";
import { buttonClass, EmptyState, ErrorState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { activeParams, hasFilters, readDashboardFilters, type RawSearchParams } from "@/lib/params";
import type { Announcement, Category, Company, Page } from "@/lib/types";

export const metadata = { title: "AI Intelligence" };

const PAGE_SIZE = 20;

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = readDashboardFilters(await searchParams);
  const [feed, categories, companies] = await Promise.all([
    load<Page<Announcement>>("/v1/announcements", {
      q: filters.q,
      category: filters.category,
      company: filters.company,
      kind: filters.kind,
      published_from: filters.from,
      published_to: filters.to,
      page: filters.page,
      page_size: PAGE_SIZE,
    }),
    load<Category[]>("/v1/categories"),
    load<Page<Company>>("/v1/companies", { page_size: 100 }),
  ]);

  const params = activeParams(filters);
  const filtered = hasFilters(filters);

  return (
    <>
      <PageHeader
        title="AI Intelligence"
        description="Announcements from the official blogs, release notes and feeds of AI companies, collected automatically. Every entry links to its original source."
      >
        <FilterBar
          filters={filters}
          categories={categories.data ?? []}
          companies={companies.data?.items ?? []}
          total={feed.data?.total ?? null}
        />
      </PageHeader>

      {feed.error ? (
        feed.error.status === 422 ? (
          <ErrorState title="Some filters are not valid" retryHref="/">
            {feed.error.message} Clear the filters to see all announcements.
          </ErrorState>
        ) : (
          <ErrorState
            title="Announcements are unavailable"
            retryHref={`/${Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""}`}
          />
        )
      ) : feed.data.total === 0 ? (
        filtered ? (
          <EmptyState
            title="No announcements match"
            action={
              <a href="/" className={buttonClass("secondary")}>
                Clear filters
              </a>
            }
          >
            Nothing in the collected announcements matches these filters. Try fewer filters or a
            different search term.
          </EmptyState>
        ) : (
          <EmptyState title="No announcements collected yet">
            The worker collects announcements from the configured official sources on a schedule.
            Check the Sources page for the status of each source.
          </EmptyState>
        )
      ) : (
        <>
          <Feed items={feed.data.items} />
          <Pagination params={params} page={feed.data.page} pages={feed.data.pages} />
          {feed.data.items.length === 0 ? (
            <EmptyState title="This page is past the end of the results">
              <a href="/" className="text-accent hover:underline">
                Go back to the first page
              </a>
            </EmptyState>
          ) : null}
        </>
      )}
    </>
  );
}
