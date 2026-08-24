import { cn } from "./cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-700 text-white border-brand-700 hover:bg-brand-800 hover:border-brand-800 " +
    "disabled:bg-brand-200 disabled:border-brand-200 disabled:text-white",
  secondary:
    "bg-surface text-ink border-line-strong hover:bg-surface-sunken " +
    "disabled:text-ink-faint disabled:bg-surface-muted",
  ghost:
    "bg-transparent text-ink-muted border-transparent hover:bg-surface-sunken hover:text-ink " +
    "disabled:text-ink-faint",
  danger:
    "bg-surface text-neg border-neg-line hover:bg-neg-soft " +
    "disabled:text-ink-faint disabled:border-line disabled:bg-surface-muted",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-9 px-4 text-sm",
};

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  /** Replaces the label while an action is in flight, so a click is never
   *  ambiguous about whether it registered. */
  busy?: boolean;
  busyLabel?: string;
};

export default function Button({
  variant = "secondary",
  size = "md",
  busy = false,
  busyLabel,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-control border font-medium",
        "transition-colors disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
    >
      {busy && <Spinner />}
      {busy && busyLabel ? busyLabel : children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("h-3.5 w-3.5 animate-spin", className)}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14.5 8A6.5 6.5 0 0 0 8 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
