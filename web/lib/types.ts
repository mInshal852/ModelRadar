/** Response types of the read-only ModelRadar API (see api/app/schemas.py). */

export type AnnouncementKind = "model_release" | "update" | "deprecation" | "research" | "other";
export type DatePrecision = "day" | "datetime";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CompanyRef {
  slug: string;
  name: string;
}

export interface CategoryRef {
  slug: string;
  name: string;
}

export interface Announcement {
  id: number;
  title: string;
  description: string | null;
  kind: AnnouncementKind;
  published_at: string | null;
  published_precision: DatePrecision | null;
  original_url: string;
  source_domain: string;
  source_name: string;
  company: CompanyRef;
  categories: CategoryRef[];
  models: string[];
}

export interface Category {
  slug: string;
  name: string;
  description: string | null;
  announcement_count: number;
  company_count: number;
  children: Category[];
}

export interface Company {
  slug: string;
  name: string;
  website_url: string;
  country: string | null;
  description: string | null;
  categories: CategoryRef[];
  announcement_count: number;
  source_count: number;
  latest_published_at: string | null;
}

export interface ModelVersion {
  display_name: string;
  version_label: string | null;
  first_announced_at: string | null;
  first_announced_precision: DatePrecision | null;
  announcement_title: string;
  announcement_url: string;
  categories: CategoryRef[];
}

export interface ModelFamily {
  slug: string;
  family_name: string;
  company: CompanyRef;
  versions: ModelVersion[];
}

export interface SourceRun {
  status: string;
  started_at: string;
  finished_at: string | null;
  http_status: number | null;
  items_found: number;
  items_new: number;
  items_filtered: number;
}

export interface Source {
  id: number;
  name: string;
  company: CompanyRef;
  kind: string;
  url: string;
  hosting: string;
  hosting_notes: string | null;
  content_scope: string;
  verification_level: string;
  verified_at: string | null;
  verification_notes: string | null;
  poll_interval_minutes: number;
  enabled: boolean;
  status: string | null;
  consecutive_failures: number;
  last_synced_at: string | null;
  last_error: string | null;
  announcement_count: number;
  last_run: SourceRun | null;
}

export interface Meta {
  announcement_count: number;
  company_count: number;
  source_count: number;
  enabled_source_count: number;
  last_synced_at: string | null;
}
