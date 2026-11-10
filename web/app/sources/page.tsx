import Link from "next/link";

import { ExternalIcon } from "@/components/icons";
import {
  HOSTING_LABELS,
  KIND_NAMES,
  SCOPE_LABELS,
  StatusBadge,
  VERIFICATION_LABELS,
} from "@/components/source-status";
import { EmptyState, ErrorState, ExternalLink, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { formatCount, formatPublished, formatRelative } from "@/lib/format";
import type { Source } from "@/lib/types";

export const metadata = { title: "Sources" };

function lastSync(source: Source) {
  const when = source.last_synced_at;
  if (!when) return <span className="text-faint">Never</span>;
  return (
    <time dateTime={when} title={formatPublished(when, "datetime").iso ?? undefined}>
      {formatRelative(when)}
    </time>
  );
}

export default async function SourcesPage() {
  const { data, error } = await load<Source[]>("/v1/sources");
  const enabled = data?.filter((s) => s.enabled).length ?? 0;

  return (
    <>
      <PageHeader
        title="Sources"
        description="Every official feed ModelRadar reads, how it is classified, and how its latest synchronisation went. All figures come from the synchronisation history."
      />

      {error ? (
        <ErrorState retryHref="/sources" />
      ) : data.length === 0 ? (
        <EmptyState title="No sources configured">
          Sources are loaded from the project configuration.
        </EmptyState>
      ) : (
        <>
          <p className="mb-4 text-sm text-muted">
            {formatCount(data.length)} sources, {formatCount(enabled)} enabled.
          </p>

          {/* Wide screens: table */}
          <div className="hidden overflow-x-auto rounded-panel border border-line lg:block">
            <table className="w-full min-w-[900px] border-collapse text-left text-sm">
              <caption className="sr-only">Configured official sources and their status</caption>
              <thead className="bg-surface text-xs text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    Source
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Type
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Hosting
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Verification
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Last sync
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">
                    Announcements
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.map((source) => (
                  <tr key={source.id} className="align-top hover:bg-surface/60">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">{source.name}</p>
                      <p className="text-muted">
                        <Link
                          href={`/?company=${source.company.slug}`}
                          className="hover:text-accent"
                        >
                          {source.company.name}
                        </Link>
                      </p>
                      <ExternalLink
                        href={source.url}
                        className="mt-0.5 inline-flex items-center gap-1 text-xs text-faint hover:text-accent"
                      >
                        {new URL(source.url).hostname}
                        <ExternalIcon width={12} height={12} />
                      </ExternalLink>
                    </td>
                    <td className="px-3 py-3 text-muted">
                      {KIND_NAMES[source.kind] ?? source.kind}
                      <p className="text-xs text-faint">
                        {SCOPE_LABELS[source.content_scope] ?? source.content_scope}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-muted">
                      {HOSTING_LABELS[source.hosting] ?? source.hosting}
                    </td>
                    <td className="px-3 py-3 text-muted">
                      {VERIFICATION_LABELS[source.verification_level] ?? source.verification_level}
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge source={source} />
                      {source.last_error && source.enabled ? (
                        <p className="mt-1 max-w-[16rem] text-xs text-danger">
                          {source.last_error}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-3 py-3 text-muted">{lastSync(source)}</td>
                    <td className="px-4 py-3 text-right text-ink">
                      {formatCount(source.announcement_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Narrow screens: one card per source */}
          <ul className="space-y-3 lg:hidden">
            {data.map((source) => (
              <li key={source.id} className="rounded-panel border border-line bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{source.name}</p>
                    <p className="text-sm text-muted">{source.company.name}</p>
                  </div>
                  <StatusBadge source={source} />
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <div>
                    <dt className="text-xs text-faint">Type</dt>
                    <dd className="text-muted">{KIND_NAMES[source.kind] ?? source.kind}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Hosting</dt>
                    <dd className="text-muted">
                      {HOSTING_LABELS[source.hosting] ?? source.hosting}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Verification</dt>
                    <dd className="text-muted">
                      {VERIFICATION_LABELS[source.verification_level] ?? source.verification_level}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Last sync</dt>
                    <dd className="text-muted">{lastSync(source)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Announcements</dt>
                    <dd className="text-muted">{formatCount(source.announcement_count)}</dd>
                  </div>
                </dl>
                {source.last_error && source.enabled ? (
                  <p className="mt-2 text-xs text-danger">{source.last_error}</p>
                ) : null}
                <ExternalLink
                  href={source.url}
                  className="mt-3 inline-flex items-center gap-1 break-all text-xs text-faint hover:text-accent"
                >
                  {source.url}
                  <ExternalIcon width={12} height={12} />
                </ExternalLink>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
