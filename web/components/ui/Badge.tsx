import { cn } from "./cn";

export type Tone = "neutral" | "positive" | "warning" | "blocking" | "info";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted border-line-strong",
  positive: "bg-pos-soft text-pos border-pos-line",
  warning: "bg-warn-soft text-warn border-warn-line",
  blocking: "bg-neg-soft text-neg border-neg-line",
  info: "bg-brand-50 text-brand-700 border-brand-200",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-ink-faint",
  positive: "bg-pos",
  warning: "bg-warn",
  blocking: "bg-neg",
  info: "bg-brand-500",
};

export default function Badge({
  tone = "neutral",
  dot = false,
  className,
  children,
  title,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5",
        "text-[11px] leading-4 font-semibold whitespace-nowrap",
        TONES[tone],
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone])} aria-hidden="true" />}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------- domain badges
 * The vocabulary the API actually returns. Kept in one place so a status
 * string never picks up a different colour on a different screen.
 */

/** corpus/09 section 5: the period lock state carried on every figure. */
export function ReconciliationBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "reconciled" || status === "locked" ? "positive" : status === "open" ? "neutral" : "warning";
  const label =
    status === "reconciled" ? "Reconciled" : status === "locked" ? "Locked" : status === "open" ? "Open period" : status;
  return (
    <Badge tone={tone} dot title={`Reconciliation status: ${status}`}>
      {label}
    </Badge>
  );
}

/** corpus/09 section 4's three severities. */
export function SeverityBadge({ severity }: { severity: string }) {
  const tone: Tone =
    severity === "blocking" ? "blocking" : severity === "warning" ? "warning" : "neutral";
  return (
    <Badge tone={tone} dot>
      {severity}
    </Badge>
  );
}

/** Load run status, report artefact status, mapping version status. */
export function StatusBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "signed" || status === "completed" || status === "loaded" || status === "approved"
      ? "positive"
      : status === "blocked" || status === "failed" || status === "rejected"
      ? "blocking"
      : status === "draft" || status === "quarantined" || status === "running" || status === "partial"
      ? "warning"
      : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}
