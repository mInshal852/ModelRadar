/**
 * Full-page navigation for changes within the dashboard (filters, search, pagination).
 *
 * Client-side transitions for same-page query changes stall in production builds of
 * Next.js 15.5.29 (see docs/DESIGN.md), so these use ordinary page loads. Moving between
 * different pages still uses client-side navigation.
 */
export function goTo(href: string): void {
  window.location.assign(href);
}
