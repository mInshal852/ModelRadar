import { cx } from "./ui";
import type { Source } from "@/lib/types";

export const HOSTING_LABELS: Record<string, string> = {
  first_party: "First-party",
  official_third_party: "Official, third-party hosted",
};

export const VERIFICATION_LABELS: Record<string, string> = {
  http_only: "Reachable only",
  content_sampled: "Content sampled",
  content_verified: "Content verified",
};

export const KIND_NAMES: Record<string, string> = {
  rss: "RSS",
  atom: "Atom",
  github: "GitHub",
  api: "API",
  sitemap: "Sitemap",
  html: "HTML page",
  manual: "Manual",
};

export const SCOPE_LABELS: Record<string, string> = {
  dedicated_ai: "AI-focused",
  mixed: "Mixed content",
};

export function statusInfo(source: Pick<Source, "enabled" | "status">): {
  label: string;
  tone: string;
} {
  if (!source.enabled) return { label: "Disabled", tone: "text-faint border-line" };
  switch (source.status) {
    case "ok":
      return { label: "Healthy", tone: "text-ok border-ok/40" };
    case "degraded":
      return { label: "Degraded", tone: "text-warn border-warn/40" };
    case "failing":
      return { label: "Failing", tone: "text-danger border-danger/40" };
    default:
      return { label: "Not synced yet", tone: "text-muted border-line" };
  }
}

export function StatusBadge({ source }: { source: Pick<Source, "enabled" | "status"> }) {
  const { label, tone } = statusInfo(source);
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-px text-xs font-medium",
        tone,
      )}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
