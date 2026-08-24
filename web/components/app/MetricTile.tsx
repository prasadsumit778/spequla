"use client";

import type { MetricTile as MetricTileShape } from "@/lib/api";
import { METRIC_UNITS } from "@/lib/metricUnits";
import { exactMetricValue, formatMetricValue } from "@/lib/format";
import Badge from "@/components/ui/Badge";
import { WarningGlyph } from "@/components/ui/States";
import Citation from "./Citation";

/**
 * corpus/08 section 3: "A tile for an unreconciled period is badged and shows
 * the reason. It is not hidden and it is not blank, because a promoter who
 * sees a blank tile assumes the product is broken rather than that the data
 * is incomplete."
 *
 * And CLAUDE.md invariant #7: a metric that did not resolve shows no number
 * at all -- not greyed out, not badged with a stale figure. The reason takes
 * the place the number would have occupied, which is why the unavailable tile
 * below is the same size and weight as the resolved one.
 */
export default function MetricTile({ tile }: { tile: MetricTileShape }) {
  if (tile.status !== "ok" || tile.value === null) return <UnavailableTile tile={tile} />;

  const unit = METRIC_UNITS[tile.metric];

  return (
    <div className="flex flex-col rounded-card border border-line bg-surface px-4 py-3.5 shadow-card">
      <p className="label-caps">{tile.label}</p>
      {/* D-056: headline metrics are shown in crores to one decimal. The
          stored figure is never out of reach -- it is on the tile as a title
          and in full in the citation trace below. */}
      <p
        className="figure mt-1.5 text-[26px] leading-8 font-semibold tracking-[-0.02em] text-ink"
        title={exactMetricValue(tile.value, unit)}
      >
        {formatMetricValue(tile.metric, tile.value, unit, "crore")}
      </p>
      <div className="mt-auto pt-3">
        {tile.citation ? (
          <Citation citation={tile.citation} />
        ) : (
          // Unreachable through /overview/tiles -- an "ok" tile always carries
          // one -- but if it ever were, the invariant decides what happens.
          <p className="text-[11.5px] text-neg">No citation returned. This figure is not traceable.</p>
        )}
      </div>
    </div>
  );
}

function UnavailableTile({ tile }: { tile: MetricTileShape }) {
  const blocking = tile.blocking_decisions?.length ? tile.blocking_decisions : null;

  return (
    <div className="flex flex-col rounded-card border border-warn-line bg-warn-soft px-4 py-3.5">
      <p className="label-caps">{tile.label}</p>
      <p className="mt-1.5 flex items-center gap-1.5 text-[15px] leading-8 font-semibold text-warn">
        <WarningGlyph className="h-4 w-4" />
        Not available
      </p>
      <p className="mt-1 text-[12.5px] leading-5 text-ink-soft">
        {tile.reason || "No reason was returned for this metric."}
      </p>
      {blocking && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {blocking.map((decision) => (
            <Badge key={decision} tone="warning" title="An open decision in corpus/00 blocks this metric">
              {decision}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
