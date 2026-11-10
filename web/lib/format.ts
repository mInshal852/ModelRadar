import type { AnnouncementKind, DatePrecision } from "./types";

const DAY = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const LONG_DAY = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const TIME = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

export const NO_DATE_LABEL = "Date not stated";

export interface PublishedDisplay {
  /** "9 Nov 2026", or "Date not stated". */
  date: string;
  /** "19:00 UTC" only when the source stated a time; never invented. */
  time: string | null;
  /** ISO date (UTC) used to group announcements by day; null when undated. */
  dayKey: string | null;
  /** Full ISO timestamp for the <time> element and tooltips. */
  iso: string | null;
}

/**
 * How to show an original publication date.
 * - Missing date: "Date not stated" (never the discovery time).
 * - Date-only (precision "day"): the date, no time.
 * - A time is shown only for precision "datetime", and not when it is exactly 00:00 UTC,
 *   because midnight is how feeds usually write a date without a time.
 */
export function formatPublished(
  iso: string | null,
  precision: DatePrecision | null,
): PublishedDisplay {
  if (!iso) return { date: NO_DATE_LABEL, time: null, dayKey: null, iso: null };
  const when = new Date(iso);
  if (Number.isNaN(when.getTime()))
    return { date: NO_DATE_LABEL, time: null, dayKey: null, iso: null };
  const midnight = when.getUTCHours() === 0 && when.getUTCMinutes() === 0;
  const showTime = precision === "datetime" && !midnight;
  return {
    date: DAY.format(when),
    time: showTime ? `${TIME.format(when)} UTC` : null,
    dayKey: when.toISOString().slice(0, 10),
    iso: when.toISOString(),
  };
}

export function formatLongDay(dayKey: string): string {
  return LONG_DAY.format(new Date(`${dayKey}T00:00:00Z`));
}

export function formatRelative(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const when = new Date(iso);
  const seconds = Math.round((now.getTime() - when.getTime()) / 1000);
  if (Number.isNaN(seconds)) return "Unknown";
  if (seconds < 0) return DAY.format(when);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)} d ago`;
  return DAY.format(when);
}

export const KIND_LABELS: Record<AnnouncementKind, string> = {
  model_release: "Model release",
  update: "Update",
  deprecation: "Deprecation",
  research: "Research",
  other: "Unclassified",
};

export const KIND_OPTIONS = (Object.keys(KIND_LABELS) as AnnouncementKind[]).map((value) => ({
  value,
  label: KIND_LABELS[value],
}));

export function isKind(value: string | undefined): value is AnnouncementKind {
  return value !== undefined && value in KIND_LABELS;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-GB").format(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

export function initials(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  const letters =
    words.length > 1 ? words.slice(0, 2).map((w) => w[0]) : [(words[0] ?? "?").slice(0, 2)];
  return letters.join("").toUpperCase();
}
