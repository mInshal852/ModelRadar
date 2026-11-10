"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import {
  AboutIcon,
  CategoriesIcon,
  CompaniesIcon,
  DashboardIcon,
  ModelsIcon,
  SourcesIcon,
} from "./icons";
import { cx } from "./ui";

export interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: DashboardIcon },
  { href: "/models", label: "Models", icon: ModelsIcon },
  { href: "/categories", label: "Categories", icon: CategoriesIcon },
  { href: "/companies", label: "Companies", icon: CompaniesIcon },
  { href: "/sources", label: "Sources", icon: SourcesIcon },
  { href: "/about", label: "About", icon: AboutIcon },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function currentSection(pathname: string): string {
  return NAV_ITEMS.find((item) => isActive(pathname, item.href))?.label ?? "ModelRadar";
}

export function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main">
      <ul className="space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          const props = {
            href,
            onClick: onNavigate,
            "aria-current": active ? ("page" as const) : undefined,
            className: cx(
              "group relative flex h-10 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors md:h-9",
              active ? "bg-raised text-ink" : "text-muted hover:bg-raised/60 hover:text-ink",
            ),
          };
          const content = (
            <>
              {active ? (
                <span
                  aria-hidden="true"
                  className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-accent"
                />
              ) : null}
              <Icon className={active ? "text-accent" : "text-faint group-hover:text-muted"} />
              {label}
            </>
          );
          return (
            <li key={href}>
              {/* The dashboard link is a plain link: going to "/" from a filtered dashboard is a
                  same-page change, which uses full page loads (see lib/navigate.ts). */}
              {href === "/" ? <a {...props}>{content}</a> : <Link {...props}>{content}</Link>}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
