"use client";

import { useState } from "react";
import { getOverviewTiles } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import PageHeader from "@/components/app/PageHeader";
import StateStrip from "@/components/app/StateStrip";
import MetricTile from "@/components/app/MetricTile";
import Button from "@/components/ui/Button";
import { Field, Toolbar } from "@/components/ui/Field";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";

/**
 * corpus/08 section 3: the landing screen. Nine headline tiles in three rows
 * of three, each carrying its citation; a tile that did not resolve shows the
 * reason in place of the number rather than going blank.
 */
export default function OverviewPage() {
  const { entityId, ready } = useWorkspace();
  const [period, setPeriod] = useState("2025-03");

  const tiles = useApiQuery(
    (token) => getOverviewTiles(token, period, entityId),
    [period, entityId],
    { enabled: ready }
  );

  return (
    <>
      <PageHeader
        title="Financial overview"
        description="The nine headline metrics for the selected month. Every figure carries a citation back to the rows it was computed from; anything that did not resolve says why."
        corpusRef="corpus/08 section 3"
        actions={
          <Button variant="secondary" onClick={tiles.reload} busy={tiles.loading} busyLabel="Loading">
            Refresh
          </Button>
        }
      />

      <Toolbar className="mb-4">
        <Field label="Period" htmlFor="overview-period">
          <input
            id="overview-period"
            type="month"
            value={period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
      </Toolbar>

      {tiles.data && (
        <StateStrip
          className="mb-4"
          period={tiles.data.period}
          reconciliationStatus={tiles.data.reconciliation_status}
          mappingVersionId={tiles.data.mapping_version_id}
        />
      )}

      {tiles.error && (
        <ErrorState
          title="The overview could not be loaded"
          message={tiles.error}
          hint="This usually means the period has no approved mapping version yet, or the entity has no data loaded. Nothing has changed in your books."
          onRetry={tiles.reload}
        />
      )}

      {!tiles.error && tiles.loading && !tiles.data && <TileSkeleton />}

      {!tiles.error && tiles.data && tiles.data.rows.length === 0 && (
        <EmptyState
          title="No metrics were returned for this period"
          description="Choose another period, or check that data has been uploaded and mapped for this entity."
        />
      )}

      {!tiles.error &&
        tiles.data?.rows.map((row) => (
          <section key={row.row} className="mb-6">
            <h2 className="mb-2 text-[13px] font-semibold tracking-[0.04em] text-ink-muted uppercase">
              {row.row}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {row.tiles.map((tile) => (
                <MetricTile key={tile.metric} tile={tile} />
              ))}
            </div>
          </section>
        ))}

      {tiles.data && (
        <p className="mt-2 max-w-3xl text-[12px] leading-5 text-ink-faint">
          corpus/08 section 3 also specifies a prior-month and prior-year change and a twelve-month sparkline on
          each tile. The overview endpoint does not return them, so they are not shown here rather than being
          estimated. The monthly pack carries the comparatives it does compute.
        </p>
      )}
    </>
  );
}

function TileSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading metrics">
      {[0, 1, 2].map((row) => (
        <section key={row} className="mb-6">
          <Skeleton className="mb-2 h-3 w-24" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((tile) => (
              <div key={tile} className="rounded-card border border-line bg-surface px-4 py-3.5 shadow-card">
                <Skeleton className="h-2.5 w-20" />
                <Skeleton className="mt-3 h-7 w-32" />
                <Skeleton className="mt-4 h-2.5 w-full" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
