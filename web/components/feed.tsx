import { AnnouncementRow } from "./announcement-row";
import { formatLongDay, formatPublished, NO_DATE_LABEL } from "@/lib/format";
import type { Announcement } from "@/lib/types";

interface DayGroup {
  key: string;
  label: string;
  items: Announcement[];
}

/** Group a page of announcements by original publication day; undated ones form the last group. */
export function groupByDay(items: Announcement[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const item of items) {
    const { dayKey } = formatPublished(item.published_at, item.published_precision);
    const key = dayKey ?? "undated";
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(item);
    } else {
      groups.push({
        key,
        label: dayKey ? formatLongDay(dayKey) : NO_DATE_LABEL,
        items: [item],
      });
    }
  }
  return groups;
}

/**
 * The feed is a dated ledger: a day label in the left gutter (above the rows on narrow
 * screens) and that day's announcements to its right.
 */
export function Feed({ items }: { items: Announcement[] }) {
  return (
    <div className="space-y-8">
      {groupByDay(items).map((group) => (
        <section
          key={group.key}
          aria-labelledby={`day-${group.key}`}
          className="md:grid md:grid-cols-[8.5rem_minmax(0,1fr)] md:gap-6"
        >
          <h2
            id={`day-${group.key}`}
            className="mb-3 text-sm font-semibold text-ink md:sticky md:top-20 md:mb-0 md:self-start md:pt-0.5"
          >
            {group.label}
          </h2>
          <div>
            {group.items.map((item) => (
              <AnnouncementRow key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
