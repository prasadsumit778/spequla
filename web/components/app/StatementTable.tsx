import { cn } from "@/components/ui/cn";

/**
 * The shared layout for anything that reads like a statement: the P&L, the
 * balance sheet groups, the consumer CM ladder, the pack's statement section.
 *
 * Conventions, applied once here so they do not drift between screens:
 * labels left, figures right in tabular numerals, subtotals ruled above and
 * set in ink, memo lines indented and muted (corpus/08 section 4.1 --
 * marketplace GMV is a memo and is never summed into revenue), and ratio
 * lines rendered as a percentage under the subtotal they qualify.
 */

export type StatementRowKind = "line" | "subtotal" | "total" | "memo" | "ratio";

export function StatementTable({
  children,
  className,
  caption,
}: {
  children: React.ReactNode;
  className?: string;
  caption?: string;
}) {
  return (
    <table className={cn("w-full border-collapse text-[13.5px]", className)}>
      {caption && <caption className="sr-only">{caption}</caption>}
      <tbody>{children}</tbody>
    </table>
  );
}

export function StatementRow({
  label,
  value,
  kind = "line",
  note,
  indent = 0,
  prefix,
  tone,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  kind?: StatementRowKind;
  /** A qualifier that belongs beside the label, not in the figure column. */
  note?: React.ReactNode;
  indent?: number;
  /** "less", "add", "=" -- the ladder's own connective, kept out of the label. */
  prefix?: string;
  tone?: "positive" | "warning" | "blocking";
}) {
  const isSubtotal = kind === "subtotal" || kind === "total";
  const isMemo = kind === "memo";
  const isRatio = kind === "ratio";

  return (
    <tr
      className={cn(
        "border-b border-line last:border-b-0",
        isSubtotal && "border-t border-line-strong",
        kind === "total" && "border-t-2 border-t-ink-soft"
      )}
    >
      <th
        scope="row"
        className={cn(
          "py-2 pr-4 text-left font-normal",
          isSubtotal && "font-semibold text-ink",
          isMemo && "text-[12.5px] text-ink-faint",
          isRatio && "text-[12.5px] text-ink-muted",
          !isSubtotal && !isMemo && !isRatio && "text-ink-soft"
        )}
        style={{ paddingLeft: indent * 16 }}
      >
        {prefix && <span className="mr-1.5 text-ink-faint">{prefix}</span>}
        {label}
        {note && <span className="ml-1.5 text-[12px] text-ink-faint">{note}</span>}
      </th>
      <td
        className={cn(
          "py-2 pl-4 text-right whitespace-nowrap tabular-nums",
          isSubtotal ? "font-semibold text-ink" : "text-ink-soft",
          isMemo && "text-[12.5px] text-ink-faint",
          isRatio && "text-[12.5px] text-ink-muted",
          tone === "positive" && "text-pos",
          tone === "warning" && "text-warn",
          tone === "blocking" && "text-neg"
        )}
      >
        {value}
      </td>
    </tr>
  );
}

/** A heading inside a statement, e.g. a balance sheet group. */
export function StatementSection({ label }: { label: string }) {
  return (
    <tr>
      <th colSpan={2} scope="colgroup" className="pt-4 pb-1 text-left label-caps">
        {label}
      </th>
    </tr>
  );
}
