import Badge from "@/components/ui/Badge";
import { WarningGlyph } from "@/components/ui/States";
import { cn } from "@/components/ui/cn";

/**
 * The inline form of the same rule the metric tile applies: where a value
 * would be, say that it is not available and why. Used in ladders, statement
 * rows and product tables, where a full tile would be too heavy.
 */
export default function NotAvailable({
  reason,
  decisions,
  className,
  compact = false,
}: {
  reason: string | null | undefined;
  decisions?: string[] | null;
  className?: string;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-[12.5px] text-warn", className)} title={reason || undefined}>
        <WarningGlyph className="h-3.5 w-3.5" />
        Not available
      </span>
    );
  }

  return (
    <div className={cn("rounded-control border border-warn-line bg-warn-soft px-3 py-2.5", className)}>
      <p className="flex items-center gap-1.5 text-[13px] font-semibold text-warn">
        <WarningGlyph className="h-4 w-4" />
        Not available
      </p>
      <p className="mt-1 text-[12.5px] leading-5 text-ink-soft">
        {reason || "No reason was returned."}
      </p>
      {decisions && decisions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {decisions.map((d) => (
            <Badge key={d} tone="warning">
              {d}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
