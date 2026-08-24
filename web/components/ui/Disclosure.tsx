"use client";

import { useState } from "react";
import { cn } from "./cn";

/**
 * Progressive disclosure for the detail a finance user needs on demand but
 * not by default: the compiled SQL, a raw artefact, a long reason. Closed by
 * default, never hiding anything that governs whether a number is
 * trustworthy -- that stays on the surface.
 */
export default function Disclosure({
  label,
  openLabel,
  defaultOpen = false,
  children,
  className,
}: {
  label: string;
  openLabel?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-brand-600 hover:text-brand-800"
      >
        <svg
          viewBox="0 0 12 12"
          className={cn("h-3 w-3 transition-transform", open && "rotate-90")}
          fill="none"
          aria-hidden="true"
        >
          <path d="m4.5 2.5 4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {open ? openLabel || label : label}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

/** Monospaced, scrollable, selectable. For SQL and stored artefacts. */
export function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <pre
      className={cn(
        "scroll-x max-h-96 overflow-y-auto rounded-control border border-line bg-surface-sunken",
        "px-3 py-2.5 font-mono text-[11.5px] leading-5 text-ink-soft",
        className
      )}
    >
      {children}
    </pre>
  );
}
