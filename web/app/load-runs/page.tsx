"use client";

import Link from "next/link";
import { listFiles, listLoadRuns } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { formatCount, formatDateTime } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import { StatusBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { EmptyState, ErrorState, SkeletonTable } from "@/components/ui/States";

/**
 * Every file that has entered the system and what happened to it. This is the
 * lineage screen: a figure on any other page traces back through a citation
 * to a source file, and this is where that file's arrival is recorded.
 */
export default function LoadRunsPage() {
  const runs = useApiQuery((token) => listLoadRuns(token), []);
  const files = useApiQuery((token) => listFiles(token), []);

  function reloadBoth() {
    runs.reload();
    files.reload();
  }

  return (
    <>
      <PageHeader
        title="Load runs"
        description="Everything that has been loaded for this company, newest first. Raw files land immutably; a load run records what each one did."
        corpusRef="corpus/04 lineage"
        actions={
          <Button variant="secondary" onClick={reloadBoth} busy={runs.loading || files.loading} busyLabel="Loading">
            Refresh
          </Button>
        }
      />

      <Card className="mb-4">
        <CardHeader
          title="Runs"
          description={runs.settled && runs.data ? `${runs.data.length} recorded` : "Loading"}
        />

        {runs.error && (
          <div className="p-5">
            <ErrorState title="Load runs could not be listed" message={runs.error} onRetry={runs.reload} />
          </div>
        )}

        {!runs.error && !runs.data && runs.loading && <SkeletonTable rows={5} cols={6} />}

        {!runs.error && runs.data?.length === 0 && (
          <EmptyState
            title="Nothing has been loaded yet"
            description="Once a file is uploaded, its load run appears here with the outcome for every row in it."
            action={
              <Link
                href="/upload"
                className="inline-flex h-9 items-center rounded-control border border-brand-700 bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800"
              >
                Upload a file
              </Link>
            }
          />
        )}

        {!runs.error && runs.data && runs.data.length > 0 && (
          <TFrame>
            <Table>
              <THead>
                <TR>
                  <TH>Run</TH>
                  <TH>Status</TH>
                  <TH>Source</TH>
                  <TH>Entity</TH>
                  <TH>Triggered by</TH>
                  <TH align="right">Started</TH>
                  <TH align="right">Completed</TH>
                </TR>
              </THead>
              <TBody>
                {runs.data.map((run) => (
                  <TR key={run.load_run_id}>
                    <TD className="font-medium text-ink">#{run.load_run_id}</TD>
                    <TD>
                      <StatusBadge status={run.status} />
                    </TD>
                    <TD>{run.source_system}</TD>
                    <TD numeric>{run.entity_id}</TD>
                    <TD className="max-w-[220px] truncate" title={run.triggered_by}>
                      {run.triggered_by}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {formatDateTime(run.started_at)}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {run.completed_at ? (
                        formatDateTime(run.completed_at)
                      ) : (
                        <span className="text-ink-faint">still running</span>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TFrame>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Files received"
          description={files.settled && files.data ? `${files.data.length} file${files.data.length === 1 ? "" : "s"}` : "Loading"}
        />

        {files.error && (
          <div className="p-5">
            <ErrorState title="Files could not be listed" message={files.error} onRetry={files.reload} />
          </div>
        )}

        {!files.error && !files.data && files.loading && <SkeletonTable rows={4} cols={5} />}

        {!files.error && files.data?.length === 0 && (
          <EmptyState
            title="No files on record"
            description="Uploaded files are listed here with the load run that read them."
          />
        )}

        {!files.error && files.data && files.data.length > 0 && (
          <TFrame>
            <Table>
              <THead>
                <TR>
                  <TH>File</TH>
                  <TH>Template</TH>
                  <TH align="right">Rows</TH>
                  <TH>Load run</TH>
                  <TH align="right">Received</TH>
                </TR>
              </THead>
              <TBody>
                {files.data.map((file) => (
                  <TR key={file.source_file_id}>
                    <TD className="max-w-[320px] font-medium break-all text-ink">{file.file_name}</TD>
                    <TD>{file.template_type}</TD>
                    <TD numeric>{formatCount(file.row_count)}</TD>
                    <TD>#{file.load_run_id}</TD>
                    <TD align="right" className="whitespace-nowrap">
                      {formatDateTime(file.received_at)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TFrame>
        )}
      </Card>
    </>
  );
}
