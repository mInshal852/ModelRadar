import Link from "next/link";

import { buttonClass, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link href="/" className={buttonClass("secondary")}>
          Go to the dashboard
        </Link>
      }
    >
      There is nothing at this address.
    </EmptyState>
  );
}
