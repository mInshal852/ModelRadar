import type { Metadata } from "next";
// Fonts are bundled from npm packages and served by this site itself (no Google Fonts / CDN).
import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/newsreader";
import "./globals.css";

import { AppShell } from "@/components/shell";
import { load } from "@/lib/api";
import { formatCount, formatRelative } from "@/lib/format";
import type { Meta } from "@/lib/types";

export const metadata: Metadata = {
  title: { default: "ModelRadar", template: "%s · ModelRadar" },
  description: "AI model announcements collected from official company sources.",
};

export const dynamic = "force-dynamic";

// Sets the theme before first paint from a preference kept only in this browser.
const THEME_SCRIPT = `(function(){var d=document.documentElement;try{var p=localStorage.getItem("modelradar-theme");if(p!=="light"&&p!=="system")p="dark";var l=p==="light"||(p==="system"&&window.matchMedia("(prefers-color-scheme: light)").matches);d.dataset.theme=l?"light":"dark";d.dataset.themePref=p}catch(e){d.dataset.theme="dark";d.dataset.themePref="dark"}})()`;

async function SidebarFooter() {
  const { data } = await load<Meta>("/v1/meta");
  if (!data) return <p>Data service unavailable.</p>;
  return (
    <div className="space-y-1">
      <p>
        <span className="text-ink">{formatCount(data.announcement_count)}</span> announcements
      </p>
      <p>
        {data.last_synced_at
          ? `Last synced ${formatRelative(data.last_synced_at)}`
          : "Not synced yet"}
      </p>
    </div>
  );
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <AppShell footer={<SidebarFooter />}>{children}</AppShell>
      </body>
    </html>
  );
}
