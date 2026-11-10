import Link from "next/link";

import { Chip, EmptyState, ErrorState, ExternalLink, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { formatPublished, plural } from "@/lib/format";
import type { ModelFamily, Page } from "@/lib/types";

export const metadata = { title: "Models" };

export default async function ModelsPage() {
  const { data, error } = await load<Page<ModelFamily>>("/v1/models", { page_size: 100 });

  return (
    <>
      <PageHeader
        title="Models"
        description="Model families and versions found in official announcements, each linked to the announcement that first mentioned it."
      />

      <div
        role="note"
        className="mb-6 max-w-3xl rounded-panel border border-signal/40 bg-signal-soft px-4 py-3 text-sm text-ink"
      >
        <strong className="font-semibold">This directory is not exhaustive.</strong> Automatic model
        detection has not been built yet, so models only appear here once they have been identified
        in an announcement. Many announced models are missing.
      </div>

      {error ? (
        <ErrorState retryHref="/models" />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No models identified yet"
          action={
            <Link href="/?kind=model_release" className="text-accent hover:underline">
              Browse model releases instead
            </Link>
          }
        >
          Announcements are being collected, but none has been matched to a model. Nothing is
          guessed: model names will appear here only when they are detected from the original text.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {data.items.map((family) => (
            <li key={`${family.company.slug}-${family.slug}`}>
              <article className="rounded-panel border border-line bg-surface p-4">
                <header className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">
                    {family.family_name}
                  </h2>
                  <p className="text-sm text-muted">
                    {family.company.name} · {plural(family.versions.length, "version")}
                  </p>
                </header>
                <ul className="mt-3 divide-y divide-line">
                  {family.versions.map((version) => {
                    const announced = formatPublished(
                      version.first_announced_at,
                      version.first_announced_precision,
                    );
                    return (
                      <li
                        key={version.display_name}
                        className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2"
                      >
                        <div className="min-w-0">
                          <p className="font-medium text-ink">{version.display_name}</p>
                          <ExternalLink
                            href={version.announcement_url}
                            className="text-sm text-muted hover:text-accent"
                          >
                            {version.announcement_title}
                          </ExternalLink>
                        </div>
                        <div className="flex items-center gap-2 text-sm text-muted">
                          <span title="Date of the earliest official announcement found">
                            First announced {announced.date}
                          </span>
                          {version.categories.map((category) => (
                            <Chip key={category.slug}>{category.name}</Chip>
                          ))}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </article>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
