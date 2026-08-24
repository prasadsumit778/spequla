import type { IconName } from "@/lib/nav";

/** One flat 20px line-icon set, drawn inline. No icon dependency, and no
 *  glyph that carries meaning a label does not already carry. */
export default function Icon({ name, className = "h-[18px] w-[18px]" }: { name: IconName; className?: string }) {
  const common = {
    viewBox: "0 0 20 20",
    fill: "none",
    className,
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "overview":
      return (
        <svg {...common}>
          <rect x="2.75" y="2.75" width="6" height="6" rx="1.2" />
          <rect x="11.25" y="2.75" width="6" height="6" rx="1.2" />
          <rect x="2.75" y="11.25" width="6" height="6" rx="1.2" />
          <rect x="11.25" y="11.25" width="6" height="6" rx="1.2" />
        </svg>
      );
    case "statements":
      return (
        <svg {...common}>
          <path d="M4.5 2.75h8.2l3 3v11.5h-11.2z" />
          <path d="M12.4 2.9v3h3" />
          <path d="M7 9.5h6M7 12.5h4" />
        </svg>
      );
    case "operating":
      return (
        <svg {...common}>
          <path d="M3 16.5V8.5M7.67 16.5V4.5M12.33 16.5v-5M17 16.5V6.5" />
        </svg>
      );
    case "ask":
      return (
        <svg {...common}>
          <path d="M17 11.5a3 3 0 0 1-3 3H8.2L4.2 17.2v-2.7H6a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3z" />
          <path d="M8.4 7.6a1.7 1.7 0 1 1 2.3 1.6c-.5.2-.7.6-.7 1.1" />
          <circle cx="10" cy="12.4" r="0.7" fill="currentColor" stroke="none" />
        </svg>
      );
    case "reports":
      return (
        <svg {...common}>
          <path d="M5 2.75h10v14.5H5z" />
          <path d="M7.75 6.5h4.5M7.75 9.5h4.5M7.75 12.5h2.5" />
        </svg>
      );
    case "upload":
      return (
        <svg {...common}>
          <path d="M10 13.2V3.4" />
          <path d="m6.4 6.8 3.6-3.5 3.6 3.5" />
          <path d="M3.25 12.5v3a1.5 1.5 0 0 0 1.5 1.5h10.5a1.5 1.5 0 0 0 1.5-1.5v-3" />
        </svg>
      );
    case "loadRuns":
      return (
        <svg {...common}>
          <ellipse cx="10" cy="5" rx="6.25" ry="2.25" />
          <path d="M3.75 5v10c0 1.24 2.8 2.25 6.25 2.25s6.25-1.01 6.25-2.25V5" />
          <path d="M16.25 10c0 1.24-2.8 2.25-6.25 2.25S3.75 11.24 3.75 10" />
        </svg>
      );
    case "mapping":
      return (
        <svg {...common}>
          <circle cx="5" cy="5" r="2.25" />
          <circle cx="5" cy="15" r="2.25" />
          <circle cx="15" cy="10" r="2.25" />
          <path d="M7.1 6.2 12.9 9M7.1 13.8 12.9 11" />
        </svg>
      );
    case "dataHealth":
      return (
        <svg {...common}>
          <path d="M2.75 10.5h3.4l1.85-4.4 2.9 8.2 1.8-3.8h4.55" />
        </svg>
      );
    case "exceptions":
      return (
        <svg {...common}>
          <path d="M10 2.9 17.6 16.6H2.4z" />
          <path d="M10 8v3.2" />
          <circle cx="10" cy="13.7" r="0.75" fill="currentColor" stroke="none" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="2.5" />
          <path d="M10 2.75v1.9M10 15.35v1.9M17.25 10h-1.9M4.65 10h-1.9M15.13 4.87l-1.34 1.34M6.21 13.79l-1.34 1.34M15.13 15.13l-1.34-1.34M6.21 6.21 4.87 4.87" />
        </svg>
      );
  }
}
