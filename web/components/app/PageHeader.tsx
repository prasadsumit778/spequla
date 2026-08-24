export default function PageHeader({
  title,
  description,
  actions,
  corpusRef,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Which specification section this screen implements. Shown quietly --
   *  it is provenance, not instruction, and it matters to the analyst
   *  signing the numbers off. */
  corpusRef?: string;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.015em]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-[13.5px] leading-6 text-ink-muted">{description}</p>}
        {corpusRef && <p className="mt-1.5 text-[11.5px] text-ink-faint">{corpusRef}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
