"use client";

import { ErrorState } from "@/components/ui";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorState title="Something went wrong">
      <p>This page could not be displayed.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 inline-flex h-9 items-center rounded-control border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink hover:bg-raised"
      >
        Try again
      </button>
    </ErrorState>
  );
}
