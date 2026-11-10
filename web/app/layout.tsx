import type { Metadata } from "next";
// Fonts are bundled from npm packages and served by this site itself (no Google Fonts / CDN).
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "ModelRadar",
  description: "Official AI model announcements, collected from official company sources.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
