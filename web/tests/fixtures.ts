import type { Announcement } from "@/lib/types";

/** Synthetic announcement used only to exercise components in unit tests. */
export function makeAnnouncement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 1,
    title: "Introducing Test Model 1",
    description: "A description from the source.",
    kind: "other",
    published_at: "2026-11-09T19:00:00Z",
    published_precision: "datetime",
    original_url: "https://example.test/posts/test-model-1",
    source_domain: "example.test",
    source_name: "Example feed",
    company: { slug: "example", name: "Example Labs" },
    categories: [{ slug: "language-reasoning", name: "Language and Reasoning" }],
    models: [],
    ...overrides,
  };
}
