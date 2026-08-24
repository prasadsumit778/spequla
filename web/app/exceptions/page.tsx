"use client";

import { useState } from "react";
import { listExceptions, resolveException, type ExceptionRow } from "@/lib/api";
import { useApiAction, useApiQuery } from "@/lib/useApi";
import { exactAmount, formatDateTime, formatPeriodKey } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import { SeverityBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, EmptyState, ErrorState, SkeletonTable } from "@/components/ui/States";

type Resolution = "accepted" | "deferred" | "resolved";

const RESOLUTIONS: { value: Resolution; label: string; help: string }[] = [
  { value: "resolved", label: "Resolved", help: "The underlying problem is fixed." },
  { value: "accepted", label: "Accept", help: "Known and acceptable. The reason is logged and appears in the pack's data quality appendix." },
  { value: "deferred", label: "Defer", help: "Deal with it later. Name the owner and the date in the reason." },
];

/**
 * corpus/09 section 4: a product surface, not a log file. Sorted by severity
 * then by rupee value descending -- always by money, never by count -- and
 * "nothing is dismissed without a reason," which is why the reason field
 * gates every one of the three buttons rather than sitting beside them.
 */
export default function ExceptionsPage() {
  const queue = useApiQuery((token) => listExceptions(token, "open"), []);
  const resolve = useApiAction(resolveException);

  const [expanded, setExpanded] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);
  const [done, setDone] = useState<{ id: number; resolution: Resolution } | null>(null);

  const rows = queue.data?.exceptions ?? [];

  function openRow(id: number) {
    setExpanded(expanded === id ? null : id);
    setNote("");
    setNoteError(null);
    resolve.clearError();
  }

  async function submit(row: ExceptionRow, resolution: Resolution) {
    if (!note.trim()) {
      setNoteError("A reason is required. Nothing is dismissed without one.");
      return;
    }
    const result = await resolve.run(row.exception_id, resolution, note.trim());
    if (!result) return;
    setDone({ id: row.exception_id, resolution });
    setExpanded(null);
    setNote("");
    queue.reload();
  }

  return (
    <>
      <PageHeader
        title="Exception queue"
        description="Everything the checks have raised and nobody has answered yet, largest exposure first. A blocking exception stops output until it is dealt with."
        corpusRef="corpus/09 section 4"
        actions={
          <Button variant="secondary" onClick={queue.reload} busy={queue.loading} busyLabel="Loading">
            Refresh
          </Button>
        }
      />

      {done && (
        <Callout tone="positive" className="mb-4">
          Exception #{done.id} marked <strong>{done.resolution}</strong>, with your reason recorded against it. It has
          left the open queue.
        </Callout>
      )}

      {queue.error && (
        <ErrorState
          title="The queue could not be loaded"
          message={queue.error}
          hint="No exception has been changed."
          onRetry={queue.reload}
          className="mb-4"
        />
      )}

      {resolve.error && (
        <ErrorState
          title="That exception was not updated"
          message={resolve.error}
          hint="It is still open, exactly as it was."
          className="mb-4"
        />
      )}

      <Card>
        <CardHeader
          title="Open exceptions"
          description={
            queue.settled
              ? `${rows.length} open · sorted by severity, then by rupee value`
              : "Loading the queue"
          }
        />

        {!queue.settled && queue.loading && <SkeletonTable rows={6} cols={5} />}

        {queue.settled && rows.length === 0 && !queue.error && (
          <EmptyState
            icon="check"
            title="Nothing is open"
            description="No exception is waiting on a decision. Statements and the monthly pack are not being held up by this queue."
          />
        )}

        {rows.length > 0 && (
          <TFrame>
            <Table>
              <THead>
                <TR>
                  <TH>Severity</TH>
                  <TH>What was raised</TH>
                  <TH>Period</TH>
                  <TH align="right">Exposure</TH>
                  <TH align="right">Raised</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {rows.map((row) => (
                  <ExceptionRowView
                    key={row.exception_id}
                    row={row}
                    expanded={expanded === row.exception_id}
                    onToggle={() => openRow(row.exception_id)}
                    note={note}
                    setNote={(value) => {
                      setNote(value);
                      if (value.trim()) setNoteError(null);
                    }}
                    noteError={noteError}
                    busy={resolve.busy}
                    onSubmit={(resolution) => submit(row, resolution)}
                  />
                ))}
              </TBody>
            </Table>
          </TFrame>
        )}
      </Card>
    </>
  );
}

function ExceptionRowView({
  row,
  expanded,
  onToggle,
  note,
  setNote,
  noteError,
  busy,
  onSubmit,
}: {
  row: ExceptionRow;
  expanded: boolean;
  onToggle: () => void;
  note: string;
  setNote: (value: string) => void;
  noteError: string | null;
  busy: boolean;
  onSubmit: (resolution: Resolution) => void;
}) {
  return (
    <>
      <TR selected={expanded}>
        <TD>
          <SeverityBadge severity={row.severity} />
        </TD>
        <TD className="max-w-md">
          <span className="text-ink">{row.description}</span>
          <span className="mt-0.5 block font-mono text-[11px] text-ink-faint">{row.exception_class}</span>
          {row.suggested_action && (
            <span className="mt-1 block text-[12px] text-ink-muted">Suggested: {row.suggested_action}</span>
          )}
          {row.object_type && (
            <span className="mt-0.5 block text-[11.5px] text-ink-faint">
              {row.object_type}
              {row.object_ref ? ` ${row.object_ref}` : ""}
            </span>
          )}
        </TD>
        <TD className="whitespace-nowrap">{row.period_key ? formatPeriodKey(row.period_key) : "—"}</TD>
        <TD numeric title="Absolute rupees: this figure has to tie to a ledger line exactly">
          {exactAmount(row.value_inr)}
        </TD>
        <TD align="right" className="whitespace-nowrap text-ink-muted">
          {formatDateTime(row.raised_at)}
        </TD>
        <TD align="right">
          <Button size="sm" variant={expanded ? "primary" : "secondary"} onClick={onToggle}>
            {expanded ? "Cancel" : "Answer"}
          </Button>
        </TD>
      </TR>

      {expanded && (
        <TR className="bg-surface-muted">
          <TD colSpan={6} className="px-4 py-4">
            <div className="max-w-3xl">
              <label htmlFor={`note-${row.exception_id}`} className="label-caps mb-1 block">
                Reason — required
              </label>
              <textarea
                id={`note-${row.exception_id}`}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="What was checked, what was concluded, and for a deferral, who owns it and by when."
                className="w-full rounded-control border border-line-strong bg-surface px-3 py-2 text-sm"
              />
              {noteError && <p className="mt-1 text-[12.5px] font-medium text-neg">{noteError}</p>}
              <p className="mt-1.5 text-[12px] text-ink-muted">
                This is written to the exception and read back in the pack&rsquo;s data quality appendix. A one-click
                dismiss produces a queue everyone empties and nobody reads.
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                {RESOLUTIONS.map((option) => (
                  <Button
                    key={option.value}
                    size="sm"
                    variant={option.value === "resolved" ? "primary" : "secondary"}
                    title={option.help}
                    busy={busy}
                    onClick={() => onSubmit(option.value)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>
          </TD>
        </TR>
      )}
    </>
  );
}
