"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useAuth } from "@workos-inc/authkit-nextjs/components";
import { uploadFile, type UploadResult } from "@/lib/api";
import { useApiAction } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { exactAmount, formatPeriodKey } from "@/lib/format";
import { roleLabel } from "@/components/app/AppShell";
import PageHeader from "@/components/app/PageHeader";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";

// Every template in corpus/01 that has a loader, per src/api/routes/upload.py.
// The descriptions say what the file *is*; they deliberately name no column
// headers, because the real export formats are open (VERIFY V-003, V-007) and
// a plausible-looking field name is worse than none.
const TEMPLATES = [
  { value: "COA", label: "Chart of accounts", blurb: "Your ledger master: every account and where it sits." },
  { value: "TB", label: "Trial balance", blurb: "Closing balances for a period. Must tie to zero exactly." },
  { value: "GL", label: "General ledger", blurb: "The journal lines themselves. The source of most figures." },
  { value: "Bank", label: "Bank statement", blurb: "Needed for books-to-bank reconciliation." },
  { value: "ConsumerSales", label: "Consumer sales", blurb: "Channel order lines, for the CM ladder." },
  { value: "MFGProduction", label: "Production output", blurb: "Volumes produced and rejected, for yield and cost per unit." },
] as const;

type TemplateValue = (typeof TEMPLATES)[number]["value"];

// Per corpus/02 section 2: only these two roles touch ingestion in P0.
const UPLOAD_ALLOWED_ROLES = new Set(["spequla_analyst", "client_finance_lead"]);

export default function UploadPage() {
  const { user, role, organizationId } = useAuth();
  const { entityId } = useWorkspace();

  const [templateType, setTemplateType] = useState<TemplateValue>("GL");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useApiAction(async (token: string, template: TemplateValue, entity: number, selected: File) =>
    // lib/api.ts's template union predates the Bank loader that
    // src/api/routes/upload.py accepts; that file is out of scope for this
    // change, so the widening happens here rather than by editing it.
    uploadFile(token, template as Parameters<typeof uploadFile>[1], entity, selected)
  );

  if (!role || !UPLOAD_ALLOWED_ROLES.has(role)) {
    return (
      <>
        <PageHeader title="Upload" corpusRef="corpus/02 section 2" />
        <Card>
          <EmptyState
            title="Uploading files is not part of your role"
            description={
              <>
                You are signed in as <strong>{role ? roleLabel(role) : "a user with no role assigned"}</strong>. Only
                the SPEQULA analyst and the client finance lead can put files into the system. Ask one of them to
                load the file, and it will appear on every screen once it has.
              </>
            }
            action={
              <Link
                href="/load-runs"
                className="inline-flex h-9 items-center rounded-control border border-line-strong px-4 text-sm font-medium hover:bg-surface-sunken"
              >
                See what has been loaded
              </Link>
            }
          />
        </Card>
      </>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setResult(null);
    const uploaded = await upload.run(templateType, entityId, file);
    if (uploaded) {
      setResult(uploaded);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <PageHeader
        title="Upload"
        description="Drop in a file and it lands immutably, with a load run recording exactly what happened to every row. Nothing is overwritten; a changed fact closes the old row and opens a new one."
        corpusRef={`corpus/01 templates · signed in as ${user?.email ?? "—"}${organizationId ? ` · org ${organizationId}` : ""}`}
      />

      <form onSubmit={handleSubmit} className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="1. What kind of file is this?" description="The template decides which loader reads it." />
          <CardBody>
            <div className="grid gap-2 sm:grid-cols-2">
              {TEMPLATES.map((template) => (
                <label
                  key={template.value}
                  className={cn(
                    "flex cursor-pointer gap-2.5 rounded-control border px-3 py-2.5 transition-colors",
                    templateType === template.value
                      ? "border-brand-500 bg-brand-50"
                      : "border-line hover:border-line-strong hover:bg-surface-muted"
                  )}
                >
                  <input
                    type="radio"
                    name="template"
                    value={template.value}
                    checked={templateType === template.value}
                    onChange={() => setTemplateType(template.value)}
                    className="mt-1"
                  />
                  <span className="min-w-0">
                    <span className="block text-[13.5px] font-medium text-ink">{template.label}</span>
                    <span className="mt-0.5 block text-[12px] leading-4 text-ink-muted">{template.blurb}</span>
                  </span>
                </label>
              ))}
            </div>
          </CardBody>

          <CardHeader title="2. The file" description="Excel or CSV, against the corpus/01 templates." />
          <CardBody>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) setFile(dropped);
              }}
              className={cn(
                "rounded-card border-2 border-dashed px-6 py-8 text-center transition-colors",
                dragging ? "border-brand-500 bg-brand-50" : "border-line-strong bg-surface-muted"
              )}
            >
              <p className="text-[13.5px] text-ink-soft">
                {file ? (
                  <>
                    <span className="font-medium text-ink">{file.name}</span>
                    <span className="block text-[12px] text-ink-muted">{(file.size / 1024).toFixed(0)} KB</span>
                  </>
                ) : (
                  "Drag a file here, or choose one"
                )}
              </p>
              <input
                ref={inputRef}
                id="upload-file"
                type="file"
                accept=".csv,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="sr-only"
              />
              <div className="mt-3 flex justify-center gap-2">
                <Button type="button" size="sm" variant="secondary" onClick={() => inputRef.current?.click()}>
                  {file ? "Choose a different file" : "Choose a file"}
                </Button>
                {file && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setFile(null);
                      if (inputRef.current) inputRef.current.value = "";
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="3. Load it" description={`Entity ${entityId} · change it in the top bar`} />
            <CardBody>
              <Button
                type="submit"
                variant="primary"
                className="w-full"
                disabled={!file}
                busy={upload.busy}
                busyLabel="Loading the file"
              >
                Upload
              </Button>
              <p className="mt-2.5 text-[12px] leading-5 text-ink-muted">
                A file that does not match its template is rejected with a readable reason — never a partial load. The
                same file uploaded twice creates no duplicate facts.
              </p>
            </CardBody>
          </Card>

          {upload.error && (
            <ErrorState
              title="This file was not loaded"
              message={upload.error}
              hint="Nothing from it entered the system. Correct the file and upload it again."
            />
          )}
        </div>
      </form>

      {result && <UploadReceipt result={result} />}
    </>
  );
}

function UploadReceipt({ result }: { result: UploadResult }) {
  const unbalanced = result.trial_balance.filter((tb) => !tb.balanced);

  return (
    <Card className="mt-4">
      <CardHeader
        title={`Load run ${result.load_run_id}`}
        description="What happened to the rows in this file"
        actions={
          <>
            <Badge tone={result.status === "loaded" || result.status === "succeeded" ? "positive" : "warning"}>
              {result.status}
            </Badge>
            <Link
              href="/load-runs"
              className="inline-flex h-8 items-center rounded-control border border-line-strong px-3 text-[13px] font-medium hover:bg-surface-sunken"
            >
              All load runs
            </Link>
          </>
        }
      />
      <CardBody>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Figure label="Inserted" value={result.inserted} />
          <Figure label="Closed and re-inserted" value={result.closed_and_reinserted} note="A changed fact, versioned" />
          <Figure label="Unchanged" value={result.unchanged} />
          <Figure
            label="Quarantined"
            value={result.quarantined_count}
            tone={result.quarantined_count > 0 ? "warn" : undefined}
          />
        </dl>

        {result.periods_touched.length > 0 && (
          <p className="mt-4 text-[13px] text-ink-muted">
            Periods touched: {result.periods_touched.map((p) => formatPeriodKey(p)).join(", ")}
          </p>
        )}
      </CardBody>

      {result.trial_balance.length > 0 && (
        <>
          <div className="border-t border-line px-5 pt-3">
            <p className="label-caps">Trial balance, per period touched</p>
            <p className="mt-0.5 text-[12px] text-ink-muted">
              Tolerance is zero. A period that does not balance does not produce a statement.
            </p>
          </div>
          <CardBody className="pt-3">
            <ul className="space-y-1.5">
              {result.trial_balance.map((tb) => (
                <li key={tb.period_key} className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="w-32 font-medium text-ink">{formatPeriodKey(tb.period_key)}</span>
                  {tb.balanced ? (
                    <Badge tone="positive" dot>
                      balances
                    </Badge>
                  ) : (
                    <>
                      <Badge tone="blocking" dot>
                        does not balance
                      </Badge>
                      <span className="tabular-nums text-neg" title="Absolute rupees">
                        out by {exactAmount(tb.total)}
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </CardBody>
        </>
      )}

      {unbalanced.length > 0 && (
        <Callout tone="blocking" className="m-5" title="These periods will not produce statements">
          {unbalanced.length === 1 ? "One period" : `${unbalanced.length} periods`} in this file did not tie to zero.
          Fix it at source and upload again — the reload closes the old rows and opens new ones, so nothing is lost.
        </Callout>
      )}
    </Card>
  );
}

function Figure({ label, value, note, tone }: { label: string; value: number; note?: string; tone?: "warn" }) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className={cn("figure mt-0.5 text-[22px] leading-7 font-semibold", tone === "warn" && "text-warn")}>
        {value}
      </dd>
      {note && <p className="text-[11.5px] leading-4 text-ink-faint">{note}</p>}
    </div>
  );
}
