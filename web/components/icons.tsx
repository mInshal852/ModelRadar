import type { SVGProps } from "react";

/** One consistent icon set: 20px grid, 1.6 stroke, round caps. Decorative by default. */
function Base({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

type IconProps = SVGProps<SVGSVGElement>;

export const DashboardIcon = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="6" height="7" rx="1.5" />
    <rect x="11" y="3" width="6" height="4" rx="1.5" />
    <rect x="3" y="12" width="6" height="5" rx="1.5" />
    <rect x="11" y="9" width="6" height="8" rx="1.5" />
  </Base>
);
export const ModelsIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6L10 2.5Z" />
    <path d="M3.5 6 10 9.5 16.5 6M10 9.5v8" />
  </Base>
);
export const CategoriesIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 4.5h6l1.5 2H17v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4.5Z" />
  </Base>
);
export const CompaniesIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 17V4.5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1V17M12 8h3a1 1 0 0 1 1 1v8M2.5 17h15" />
    <path d="M7 7h2M7 10h2M7 13h2" />
  </Base>
);
export const SourcesIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 4.5a11.5 11.5 0 0 1 11.5 11.5M4 9a7 7 0 0 1 7 7" />
    <circle cx="4.8" cy="15.2" r="1.2" fill="currentColor" stroke="none" />
  </Base>
);
export const AboutIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="10" cy="10" r="7" />
    <path d="M10 9v4.5M10 6.5v.01" />
  </Base>
);
export const SearchIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="9" cy="9" r="5.5" />
    <path d="m13.2 13.2 3.3 3.3" />
  </Base>
);
export const SunIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="10" cy="10" r="3.3" />
    <path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M4.7 15.3 6 14M14 6l1.3-1.3" />
  </Base>
);
export const MoonIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M16.5 11.5A6.5 6.5 0 0 1 8.5 3.5a6.5 6.5 0 1 0 8 8Z" />
  </Base>
);
export const SystemIcon = (p: IconProps) => (
  <Base {...p}>
    <rect x="2.5" y="3.5" width="15" height="10" rx="1.5" />
    <path d="M7 17h6M10 13.5V17" />
  </Base>
);
export const ExternalIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M8 4H5a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 5 16h9a1.5 1.5 0 0 0 1.5-1.5V12M11 3.5h5.5V9M16.5 3.5 9 11" />
  </Base>
);
export const MenuIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 5.5h14M3 10h14M3 14.5h14" />
  </Base>
);
export const CloseIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="m5 5 10 10M15 5 5 15" />
  </Base>
);
export const ChevronLeftIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 5-5 5 5 5" />
  </Base>
);
export const ChevronRightIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="m8 5 5 5-5 5" />
  </Base>
);
export const AlertIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M10 3 18 16.5H2L10 3Z" />
    <path d="M10 8.5v3.5M10 14.3v.01" />
  </Base>
);
export const InboxIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 11.5 5 4.5h10l2 7M3 11.5V15a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5M3 11.5h4l1 2h4l1-2h4" />
  </Base>
);

/** Brand mark: a quiet sweep of three arcs. */
export const RadarMark = (p: IconProps) => (
  <Base viewBox="0 0 24 24" width="22" height="22" strokeWidth="1.7" {...p}>
    <path d="M12 21a9 9 0 1 1 9-9" />
    <path d="M12 16.5a4.5 4.5 0 1 1 4.5-4.5" />
    <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
    <path d="m12 12 6.4-6.4" />
  </Base>
);
