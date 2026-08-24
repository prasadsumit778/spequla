import { cn } from "./cn";
import Button from "./Button";

/* ---------------------------------------------------------------- skeletons */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-surface-sunken", className)} aria-hidden="true" />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", i === lines - 1 ? "w-2/5" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="px-5 py-4" role="status" aria-label="Loading">
      <div className="flex gap-3 border-b border-line pb-2">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-2.5 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3 border-b border-line py-3 last:border-b-0">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-3 flex-1", c === 0 && "flex-[2]")} />
          ))}
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- empty state */

export function EmptyState({
  title,
  description,
  action,
  icon = "empty",
  className,
}: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  icon?: "empty" | "search" | "check";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <StateIcon kind={icon} />
      <h3 className="mt-3 text-sm font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-md text-[13px] text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* -------------------------------------------------------------- error state */

/**
 * A failed request is a finance event, not a stack trace. The backend's
 * `detail` is written for this reader -- "balance sheet does not balance as
 * of ...", "no approved mapping version" -- so it is shown verbatim, framed
 * by what it means for the numbers on screen.
 */
export function ErrorState({
  title = "This could not be shown",
  message,
  hint,
  onRetry,
  retryLabel = "Try again",
  className,
}: {
  title?: string;
  message: string;
  hint?: React.ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("rounded-card border border-neg-line bg-neg-soft px-5 py-4", className)}
    >
      <div className="flex gap-3">
        <WarningGlyph className="mt-0.5 h-4 w-4 shrink-0 text-neg" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-neg">{title}</h3>
          <p className="mt-1 text-[13px] break-words text-ink-soft">{message}</p>
          {hint && <p className="mt-2 text-[13px] text-ink-muted">{hint}</p>}
          {onRetry && (
            <Button size="sm" variant="secondary" className="mt-3" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- callouts */

export function Callout({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "warning" | "blocking" | "positive" | "neutral";
  title?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  const tones = {
    info: "border-brand-200 bg-brand-50 text-brand-800",
    warning: "border-warn-line bg-warn-soft text-warn",
    blocking: "border-neg-line bg-neg-soft text-neg",
    positive: "border-pos-line bg-pos-soft text-pos",
    neutral: "border-line bg-surface-muted text-ink-muted",
  } as const;
  return (
    <div className={cn("rounded-card border px-4 py-3 text-[13px]", tones[tone], className)}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={cn("text-ink-soft", title ? "mt-1" : null)}>{children}</div>}
    </div>
  );
}

/* -------------------------------------------------------------------- glyphs */

export function WarningGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <path
        d="M8 1.8 14.7 13.5H1.3L8 1.8Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M8 6v3.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="11.6" r="0.85" fill="currentColor" />
    </svg>
  );
}

function StateIcon({ kind }: { kind: "empty" | "search" | "check" }) {
  const common = "h-9 w-9 text-ink-faint";
  if (kind === "search") {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={common} aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="m15.5 15.5 4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === "check") {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={cn(common, "text-pos")} aria-hidden="true">
        <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="m8.5 12.2 2.4 2.4 4.6-5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" className={common} aria-hidden="true">
      <rect x="3.5" y="5" width="17" height="14" rx="2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3.5 9.5h17M9 5v14" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
