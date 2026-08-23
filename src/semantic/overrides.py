"""The metric override resolution chain.

Implements corpus/05a's `_resolution_order`:

    entity_override -> company_override -> industry_pack -> global_default

`industry_pack` is skipped outright -- "not present in P0. Reserved so its
later arrival changes nothing" (corpus/05a) -- so this chain has three
effective layers, not four. `global_default` is config/metrics/ itself
(corpus-authored, never edited per company); this module resolves whichever
of the other two a specific tenant has actually declared, reading
db/migrations/tenant/0012_metric_definition.sql's table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class ResolvedParameters:
    parameters: dict[str, Any]
    source: str          # 'entity_override' | 'company_override' | 'global_default'
    definition_version: int | None = None
    approved_by: str | None = None


def _fetch_approved_definition(conn, schema: str, tenant_id: str, metric_id: str,
                                  entity_id: int | None, as_of: date) -> tuple[dict, int, str] | None:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT parameters, version_no, approved_by FROM "{schema}".metric_definition '
            f"WHERE tenant_id = %s AND metric_id = %s AND entity_id IS NOT DISTINCT FROM %s "
            f"AND status = 'approved' AND effective_from <= %s AND effective_to > %s "
            f'ORDER BY version_no DESC LIMIT 1',
            (tenant_id, metric_id, entity_id, as_of, as_of),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return row[0], row[1], row[2]


def resolve_parameters(conn, schema: str, tenant_id: str, metric_id: str, entity_id: int,
                         as_of: date, global_default: dict[str, Any]) -> ResolvedParameters:
    """Walks entity_override -> company_override -> global_default. Returns
    the full effective parameter set: the global default merged with
    whichever override layer matched, override values winning per key."""
    entity_row = _fetch_approved_definition(conn, schema, tenant_id, metric_id, entity_id, as_of)
    if entity_row is not None:
        params, version, approved_by = entity_row
        return ResolvedParameters({**global_default, **params}, "entity_override", version, approved_by)

    company_row = _fetch_approved_definition(conn, schema, tenant_id, metric_id, None, as_of)
    if company_row is not None:
        params, version, approved_by = company_row
        return ResolvedParameters({**global_default, **params}, "company_override", version, approved_by)

    return ResolvedParameters(dict(global_default), "global_default", None, None)
