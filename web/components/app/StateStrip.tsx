import Badge, { ReconciliationBadge } from "@/components/ui/Badge";
import { formatAmount, formatPeriodKey, isNonZeroAmount } from "@/lib/format";
import { cn } from "@/components/ui/cn";

/**
 * corpus/08 section 1: "State is always visible. Last synced, reconciliation
 * status and unmapped rupee value sit on the screen permanently, not behind
 * a menu. A user should never have to go looking for a reason to distrust a
 * figure."
 *
 * So this strip is not a summary widget -- it is the reason the numbers below
 * it can be believed, and it renders even when everything is fine.
 */
export default function StateStrip({
  period,
  reconciliationStatus,
  mappingVersionId,
  unmappedValueInr,
  extra,
  className,
}: {
  period?: string | null;
  reconciliationStatus?: string | null;
  mappingVersionId?: number | null;
  /** The rupee figure, never a percentage -- corpus/09 section 6. */
  unmappedValueInr?: string | null;
  extra?: React.ReactNode;
  className?: string;
}) {
  const unmappedPresent = isNonZeroAmount(unmappedValueInr);

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-6 gap-y-2 rounded-card border border-line bg-surface px-4 py-2.5 shadow-card",
        className
      )}
    >
      {period && (
        <Item label="Period">
          <span className="text-[13px] font-medium text-ink">{formatPeriodKey(period)}</span>
        </Item>
      )}

      {reconciliationStatus != null && (
        <Item label="Reconciliation">
          <ReconciliationBadge status={reconciliationStatus} />
        </Item>
      )}

      {mappingVersionId !== undefined && (
        <Item label="Mapping">
          {mappingVersionId === null ? (
            <Badge tone="warning">No approved version</Badge>
          ) : (
            <span className="text-[13px] font-medium text-ink">Version {mappingVersionId}</span>
          )}
        </Item>
      )}

      {unmappedValueInr !== undefined && unmappedValueInr !== null && (
        <Item label="Unmapped value">
          <span className={cn("text-[13px] font-semibold", unmappedPresent ? "text-warn" : "text-pos")}>
            {formatAmount(unmappedValueInr)}
          </span>
        </Item>
      )}

      {extra}
    </div>
  );
}

export function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="label-caps">{label}</span>
      {children}
    </div>
  );
}
