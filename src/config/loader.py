"""The refusing config loader.

Implements: corpus/12 sprint 0 item 1 -- "Build a loader that refuses to start
the application if a metric contract references a decision whose status is
open. That metric must return 'not yet configured for your company' naming the
decision, not a default value."

The application itself starts regardless of how many decisions are open --
open per-company decisions (D-001, D-002, D-006, D-012, D-015, D-016, D-017,
D-018, D-041, D-042, D-050) are normal at this stage of the corpus, per
corpus/00 section 2b ("None of these block the build"). What refuses is a
single metric, at resolution time, when something actually tries to use it.
This mirrors corpus/05a's own `_compilation_gate` rule and CLAUDE.md invariant
"No metric formula exists outside the registry": the loader is the only place
that decides whether a metric may be served, so nothing downstream can
accidentally fall back to a default.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.config.schema import Decision, MetricContractFile, TaxonomyClass

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class MetricNotConfigured(Exception):
    """Raised when a metric is asked for but one of its governing decisions is open.

    Carries exactly what CLAUDE.md section 4's escalation format asks for: which
    decision is blocking, and nothing else is guessed in its place.
    """

    def __init__(self, metric_id: str, blocking: list[str]):
        self.metric_id = metric_id
        self.blocking = blocking
        joined = ", ".join(blocking)
        super().__init__(
            f"not yet configured for your company: blocked by {joined}"
        )


@dataclass
class ConfigRegistry:
    decisions: dict[str, Decision]
    taxonomy: list[TaxonomyClass]
    metrics: dict[str, MetricContractFile]
    _blocked: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self):
        open_ids = {d.id for d in self.decisions.values() if d.status == "open"}
        for metric_id, contract in self.metrics.items():
            blocking = [d for d in contract.registry.governed_by if d in open_ids]
            if blocking:
                self._blocked[metric_id] = blocking

    @property
    def blocked_metrics(self) -> dict[str, list[str]]:
        """metric_id -> list of open decision ids blocking it."""
        return dict(self._blocked)

    def resolve_metric(self, metric_id: str) -> MetricContractFile:
        """Return the metric contract, or raise MetricNotConfigured.

        Never returns a default value for a blocked metric. This is the single
        enforcement point for the compilation gate described in corpus/05a.
        """
        if metric_id not in self.metrics:
            raise KeyError(f"unknown metric_id: {metric_id!r}")
        if metric_id in self._blocked:
            raise MetricNotConfigured(metric_id, self._blocked[metric_id])
        return self.metrics[metric_id]


def load_decisions() -> dict[str, Decision]:
    raw = yaml.safe_load((CONFIG_DIR / "decisions.yml").read_text())
    return {r["id"]: Decision(**r) for r in raw}


def load_taxonomy() -> list[TaxonomyClass]:
    raw = yaml.safe_load((CONFIG_DIR / "taxonomy.yml").read_text())
    return [TaxonomyClass(**r) for r in raw]


def load_metrics() -> dict[str, MetricContractFile]:
    out = {}
    for path in sorted((CONFIG_DIR / "metrics").glob("*.yml")):
        raw = yaml.safe_load(path.read_text())
        out[raw["registry"]["metric_id"]] = MetricContractFile(**raw)
    return out


def load_registry() -> ConfigRegistry:
    return ConfigRegistry(
        decisions=load_decisions(),
        taxonomy=load_taxonomy(),
        metrics=load_metrics(),
    )


def _verify(registry: ConfigRegistry) -> bool:
    """Sprint 0 acceptance check: 53 of 61 metrics compile, 8 do not."""
    n_total = len(registry.metrics)
    n_blocked = len(registry.blocked_metrics)
    n_ok = n_total - n_blocked
    print(f"Loaded {n_total} metric contracts, {len(registry.decisions)} decisions, "
          f"{len(registry.taxonomy)} taxonomy classes.")
    print(f"Compiles: {n_ok}, blocked: {n_blocked}")
    for metric_id, blocking in sorted(registry.blocked_metrics.items()):
        print(f"  {metric_id}: blocked by {', '.join(blocking)}")

    if n_total != 61 or n_ok != 53 or n_blocked != 8:
        print(f"MISMATCH: expected 61 total / 53 compile / 8 blocked, got "
              f"{n_total} / {n_ok} / {n_blocked}. Stopping per instruction.", file=sys.stderr)
        return False
    print("Matches the expected 53/8 split.")
    return True


if __name__ == "__main__":
    reg = load_registry()
    ok = _verify(reg)
    sys.exit(0 if ok else 1)
