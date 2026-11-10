import { isKind } from "./format";

export type RawSearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

export interface DashboardFilters {
  q: string;
  category: string;
  company: string;
  kind: string;
  from: string;
  to: string;
  page: number;
}

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Read and sanitise the dashboard's URL query. Invalid values are dropped, not forwarded. */
export function readDashboardFilters(raw: RawSearchParams): DashboardFilters {
  const page = Number.parseInt(first(raw.page), 10);
  const kind = first(raw.kind);
  return {
    q: first(raw.q).slice(0, 100),
    category: SLUG.test(first(raw.category)) ? first(raw.category) : "",
    company: SLUG.test(first(raw.company)) ? first(raw.company) : "",
    kind: isKind(kind) ? kind : "",
    from: DATE.test(first(raw.from)) ? first(raw.from) : "",
    to: DATE.test(first(raw.to)) ? first(raw.to) : "",
    page: Number.isFinite(page) && page >= 1 ? Math.min(page, 100000) : 1,
  };
}

/** Query parameters (other than `page`) that identify the current filtered view. */
export function activeParams(filters: DashboardFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of ["q", "category", "company", "kind", "from", "to"] as const) {
    if (filters[key]) out[key] = filters[key];
  }
  return out;
}

export function hasFilters(filters: DashboardFilters): boolean {
  return Object.keys(activeParams(filters)).length > 0;
}
