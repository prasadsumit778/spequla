import { cn } from "./cn";

/** A horizontally scrollable frame. Wide financial tables scroll inside
 *  their own card rather than pushing the page sideways. */
export function TableFrame({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("scroll-x", className)}>{children}</div>;
}

export function Table({ className, children }: { className?: string; children: React.ReactNode }) {
  return <table className={cn("w-full border-collapse text-[13px]", className)}>{children}</table>;
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="border-b border-line-strong">{children}</thead>;
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function TR({
  className,
  children,
  onClick,
  selected,
}: {
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "border-b border-line last:border-b-0",
        onClick && "cursor-pointer hover:bg-surface-muted",
        selected && "bg-brand-50",
        className
      )}
    >
      {children}
    </tr>
  );
}

export function TH({
  className,
  children,
  align = "left",
  scope = "col",
}: {
  className?: string;
  children?: React.ReactNode;
  align?: "left" | "right" | "center";
  scope?: "col" | "row";
}) {
  return (
    <th
      scope={scope}
      className={cn(
        "px-3 py-2 text-[11px] font-semibold tracking-[0.06em] text-ink-faint uppercase whitespace-nowrap",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className
      )}
    >
      {children}
    </th>
  );
}

export function TD({
  className,
  children,
  align = "left",
  numeric = false,
  colSpan,
  title,
}: {
  className?: string;
  children?: React.ReactNode;
  align?: "left" | "right" | "center";
  /** Right-aligns and locks digit width. Every rupee column uses it. */
  numeric?: boolean;
  colSpan?: number;
  /** Usually the exact stored figure behind a rounded one. */
  title?: string;
}) {
  const resolvedAlign = numeric ? "right" : align;
  return (
    <td
      colSpan={colSpan}
      title={title}
      className={cn(
        "px-3 py-2 align-top text-ink-soft",
        resolvedAlign === "right" && "text-right",
        resolvedAlign === "center" && "text-center",
        numeric && "font-medium text-ink whitespace-nowrap",
        className
      )}
    >
      {children}
    </td>
  );
}
