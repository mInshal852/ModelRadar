import { ExternalIcon } from "./icons";
import { Chip, KindBadge, Monogram } from "./ui";
import { formatPublished } from "@/lib/format";
import type { Announcement } from "@/lib/types";

/**
 * One announcement. Title and description are shown exactly as stored. The whole row opens the
 * original official page; category chips stay independently clickable above the row link.
 */
export function AnnouncementRow({ item }: { item: Announcement }) {
  const published = formatPublished(item.published_at, item.published_precision);

  return (
    <article className="group relative border-t border-line py-4 first:border-t-0 first:pt-0 md:pl-1">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm text-muted">
        <Monogram name={item.company.name} size="sm" />
        <span className="font-medium text-ink">{item.company.name}</span>
        <KindBadge kind={item.kind} />
        <span className="text-faint" aria-hidden="true">
          /
        </span>
        <span>{item.source_domain}</span>
        {published.iso ? (
          <time dateTime={published.iso} title={published.iso} className="text-faint">
            {published.date}
            {published.time ? ` ${published.time}` : ""}
          </time>
        ) : (
          <span className="text-faint">{published.date}</span>
        )}
      </div>

      <h3 className="font-title mt-2 text-xl font-semibold leading-snug tracking-tight text-ink">
        <a
          href={item.original_url}
          target="_blank"
          rel="noopener noreferrer"
          className="after:absolute after:inset-0 after:content-[''] hover:text-accent"
        >
          {item.title}
          <span className="sr-only">
            {" "}
            (opens the original announcement on {item.source_domain})
          </span>
        </a>
      </h3>

      {item.description ? (
        <p className="mt-1.5 line-clamp-2 max-w-[75ch] text-base text-muted">{item.description}</p>
      ) : null}

      <div className="relative z-10 mt-3 flex flex-wrap items-center gap-1.5">
        {item.models.map((model) => (
          <Chip key={model} tone="model">
            {model}
          </Chip>
        ))}
        {item.categories.map((category) => (
          <Chip key={category.slug} href={`/?category=${category.slug}`}>
            {category.name}
          </Chip>
        ))}
        <span className="ml-auto inline-flex items-center gap-1 text-xs text-faint group-hover:text-accent">
          <ExternalIcon width={14} height={14} />
          Original source
        </span>
      </div>
    </article>
  );
}
