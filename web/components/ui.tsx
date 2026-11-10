import type { ReactNode } from "react";

import { AlertIcon, InboxIcon } from "./icons";
import { initials, KIND_LABELS } from "@/lib/format";
import type { AnnouncementKind } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-6 max-w-3xl">
      <h1 className="font-title text-3xl font-semibold tracking-tight text-ink">{title}</h1>
      {description ? <p className="mt-2 max-w-[62ch] text-base text-muted">{description}</p> : null}
      {children ? <div className="mt-5">{children}</div> : null}
    </header>
  );
}

export function Monogram({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  const dims = { sm: "h-5 w-5 text-[10px]", md: "h-7 w-7 text-xs", lg: "h-10 w-10 text-sm" }[size];
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-control border border-line-strong bg-raised font-semibold text-muted",
        dims,
      )}
    >
      {initials(name)}
    </span>
  );
}

export function KindBadge({ kind }: { kind: AnnouncementKind }) {
  const styles: Record<AnnouncementKind, string> = {
    model_release: "border-signal/40 bg-signal-soft text-signal",
    update: "border-accent/40 bg-accent-soft text-accent",
    deprecation: "border-danger/40 bg-transparent text-danger",
    research: "border-line-strong bg-raised text-ink",
    other: "border-line bg-transparent text-muted",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full border px-2 py-px text-xs font-medium",
        styles[kind],
      )}
    >
      {KIND_LABELS[kind]}
    </span>
  );
}

export function Chip({
  children,
  href,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  href?: string;
  tone?: "neutral" | "model";
  className?: string;
}) {
  const classes = cx(
    "inline-flex items-center rounded-full border px-2 py-px text-xs transition-colors",
    tone === "model"
      ? "border-signal/40 bg-signal-soft text-signal"
      : "border-line text-muted hover:border-line-strong hover:text-ink",
    className,
  );
  return href ? (
    <a href={href} className={classes}>
      {children}
    </a>
  ) : (
    <span className={classes}>{children}</span>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role="status"
      className="flex flex-col items-center rounded-panel border border-dashed border-line-strong px-6 py-14 text-center"
    >
      <InboxIcon width={28} height={28} className="text-faint" />
      <h2 className="mt-3 text-lg font-semibold text-ink">{title}</h2>
      {children ? <div className="mt-1 max-w-[52ch] text-muted">{children}</div> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Could not load this page",
  children,
  retryHref,
}: {
  title?: string;
  children?: ReactNode;
  retryHref?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-panel border border-danger/40 px-6 py-14 text-center"
    >
      <AlertIcon width={28} height={28} className="text-danger" />
      <h2 className="mt-3 text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-1 max-w-[52ch] text-muted">
        {children ??
          "The data service is not responding. Nothing has been lost; try again shortly."}
      </div>
      {retryHref ? (
        <a href={retryHref} className={buttonClass("secondary", "mt-5")}>
          Try again
        </a>
      ) : null}
    </div>
  );
}

export function buttonClass(
  variant: "primary" | "secondary" | "ghost" = "secondary",
  extra?: string,
) {
  const base =
    "inline-flex h-9 items-center justify-center gap-2 rounded-control px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    primary: "bg-accent text-accent-ink hover:brightness-110",
    secondary: "border border-line-strong bg-surface text-ink hover:bg-raised",
    ghost: "text-muted hover:bg-raised hover:text-ink",
  };
  return cx(base, variants[variant], extra);
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("skeleton", className)} />;
}

export function ExternalLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}
