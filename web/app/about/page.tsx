import Link from "next/link";

import { PageHeader } from "@/components/ui";

export const metadata = { title: "About" };

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "What ModelRadar does",
    body: [
      "ModelRadar collects announcements from the official blogs, release notes and feeds of AI companies and lists them in one place, newest first. Each entry shows the original title and excerpt and links to the page where the company published it.",
    ],
  },
  {
    title: "Why it exists",
    body: [
      "Releases from AI companies are spread across many sites and formats. ModelRadar gathers them so you can follow what was announced without watching each source yourself, and always reach the original.",
    ],
  },
  {
    title: "Public data only",
    body: [
      "ModelRadar has no accounts, no sign-in and no admin area, and it does not collect personal information. It uses no analytics or tracking and sets no cookies. Your choice of light or dark theme is kept only in your own browser. Fonts are served from this site.",
    ],
  },
  {
    title: "Official sources only",
    body: [
      "Every announcement comes from a source that belongs to the company that published it: its own site, or an official feed it provides. Third-party news coverage is not used. The Sources page lists each source, how it is hosted and verified, and when it was last synchronised.",
    ],
  },
  {
    title: "Limitations",
    body: [
      "Coverage is limited to the sources that have been configured and verified so far. Some companies do not publish a feed and are not included yet.",
      "Titles and excerpts are shown exactly as the sources publish them. Dates are the original publication dates; when a source states none, the entry shows “Date not stated”.",
      "Announcements are not yet classified individually. Their categories come from the publishing company, and many are labelled “Unclassified”.",
    ],
  },
  {
    title: "The model directory is not exhaustive",
    body: [
      "Models are listed only when they have been identified in an announcement. Automatic model detection is not built yet, so the Models page is incomplete and may be empty. Absence from it does not mean a model does not exist.",
    ],
  },
];

export default function AboutPage() {
  return (
    <>
      <PageHeader
        title="About ModelRadar"
        description="A read-only index of what AI companies announce, built on their own publications."
      />
      <div className="max-w-[68ch] space-y-8">
        {SECTIONS.map((section) => (
          <section key={section.title} aria-labelledby={section.title.replace(/\W+/g, "-")}>
            <h2
              id={section.title.replace(/\W+/g, "-")}
              className="font-title text-xl font-semibold tracking-tight text-ink"
            >
              {section.title}
            </h2>
            {section.body.map((paragraph) => (
              <p key={paragraph} className="mt-2 text-base text-muted">
                {paragraph}
              </p>
            ))}
          </section>
        ))}
        <p className="border-t border-line pt-6 text-sm text-muted">
          See the{" "}
          <Link href="/sources" className="text-accent hover:underline">
            Sources
          </Link>{" "}
          and{" "}
          <Link href="/categories" className="text-accent hover:underline">
            Categories
          </Link>{" "}
          pages for what is covered.
        </p>
      </div>
    </>
  );
}
