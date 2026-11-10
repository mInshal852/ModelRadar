import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="mt-3 h-5 w-full max-w-xl" />
      <Skeleton className="mt-6 h-11 w-full max-w-xl" />
      <div className="mt-8 space-y-7">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="space-y-2.5">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-6 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ))}
      </div>
      <span className="sr-only">Loading content</span>
    </div>
  );
}
