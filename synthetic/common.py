"""Shared helpers for the synthetic reference dataset generator.

Implements corpus/11_SPEQULA_EVALUATION_FRAMEWORK.md section 2: "Everything in
it is invented. It is labelled synthetic in every file, every table and every
screen it appears on, and it is never mixed with real tenant data." Every
writer in synthetic/ stamps SYNTHETIC_MARKER-derived values into the data
itself (ledger names, narrations, party names all carry a synthetic tag), not
just in a filename.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SYNTHETIC_TAG = "SYNTHETIC"

FISCAL_MONTHS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]  # April .. March, per D-038


def fiscal_year_of(d: date) -> int:
    """FY label year (FY2027 = Apr 2026 to Mar 2027), per corpus/04 section 3.1."""
    return d.year + 1 if d.month >= 4 else d.year


def period_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_range(start: date, n_months: int) -> list[date]:
    """n_months consecutive month-start dates beginning at start (day=1)."""
    out = []
    y, m = start.year, start.month
    for _ in range(n_months):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    nxt = date(d.year, d.month + 1, 1)
    from datetime import timedelta
    return nxt - timedelta(days=1)


def money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Rng:
    """Thin wrapper so every generator module shares one deterministic stream."""
    seed: int

    def __post_init__(self):
        self._r = random.Random(self.seed)

    def __getattr__(self, item):
        return getattr(self._r, item)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)
