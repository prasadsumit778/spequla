"""Formula evaluation for the deterministic compiler.

Two small, separate evaluators, matching the two formula shapes actually
used in config/metrics/*.yml (transcribed verbatim from corpus/05 and
corpus/05a -- see src/semantic/compiler.py for how each metric is routed to
one or the other):

  - `gl_class(...)` expressions -- leaf metrics with no dependencies, whose
    value is a sum over canonical classes. Patterns are an exact class name,
    a `prefix.*` wildcard, or a `|`-separated list of exact class names,
    combined with `+`/`-`. Evaluated against a {canonical_class: Decimal}
    dict already fetched from fact_gl_entry (src/reports/query.py's
    class_balances/class_movements -- reused rather than duplicated, so
    statement assembly and metric compilation read the mapping identically).

  - `metric.X op metric.Y ...` expressions -- derived metrics, evaluated
    against a {metric_id: Decimal} dict of already-compiled dependency
    values. Parsed with `ast` and walked against an explicit allow-list
    (Constant, Name, BinOp with Add/Sub/Mult/Div, UnaryOp negation,
    parentheses) rather than passed to `eval()` -- the formula strings come
    from our own corpus-derived config, not user input, but there is no
    reason to hold open a wider execution surface than four arithmetic
    operators need.

Neither evaluator invents a financial meaning for a formula token it does
not recognise -- an unparseable formula raises, per CLAUDE.md 3.1, rather
than falling back to a guess.
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation


class FormulaError(Exception):
    """The formula string could not be parsed or evaluated -- never silently
    coerced to a partial result."""


class DivideByZero(Exception):
    """A ratio's denominator was zero. Carries no value -- corpus/05a's own
    guard on gross_margin_pct: 'never zero, never null, never a divide-by-
    zero error surfaced to the user', i.e. the caller must catch this and
    report 'undefined' with the reason, not propagate a Python exception."""


# Per corpus/03 section 1: Dr positive, Cr negative in fact_gl_entry's raw
# amount_base storage -- but a metric's formula is written the way a person
# reads a balance sheet ("gross less accumulated depreciation"), which only
# nets correctly if gl_class(X) returns each class's own natural-positive
# magnitude first, with the formula's own +/- doing the human arithmetic on
# top. This mirrors src/ingest/canonical.py's NORMAL_BALANCE_BY_ACCOUNT_TYPE
# (asset/expense = Dr, liability/income/equity = Cr) applied per canonical
# class rather than per source account type, with the one accounting
# exception a class taxonomy always has to carry explicitly: accumulated
# depreciation is filed under asset.* but is itself a contra-asset with a
# natural CREDIT balance (src/reports/statement_lines.py's BALANCE_SHEET_LINES
# documents the same exception for its own, differently-shaped, bucket-sum
# arithmetic).
_CREDIT_NATURAL_PREFIXES = ("revenue.", "liability.", "equity.", "other_income.")
_CREDIT_NATURAL_EXCEPTIONS = {"asset.accumulated_depreciation"}


def class_is_credit_natural(canonical_class: str) -> bool:
    if canonical_class in _CREDIT_NATURAL_EXCEPTIONS:
        return True
    return canonical_class.startswith(_CREDIT_NATURAL_PREFIXES)


def natural_positive(canonical_class: str, raw_amount: Decimal) -> Decimal:
    """raw_amount as fetched from fact_gl_entry (Dr positive, Cr negative) ->
    this class's own natural-positive magnitude."""
    return -raw_amount if class_is_credit_natural(canonical_class) else raw_amount


_GL_CLASS_TERM = re.compile(r"gl_class\(([^)]+)\)")


def match_gl_classes(pattern: str, known_classes: list[str]) -> list[str]:
    """pattern: one gl_class(...) argument, e.g. 'asset.cash_bank',
    'liability.debt_*', or 'a.x|a.y|a.z'. known_classes: every canonical
    class in the taxonomy (config/taxonomy.yml), not just the ones with
    fetched activity -- a class with zero net movement this period is a
    real, in-scope zero, not an absent match."""
    matched: list[str] = []
    for part in pattern.split("|"):
        part = part.strip()
        if part.endswith("*"):
            prefix = part[:-1]
            matched.extend(c for c in known_classes if c.startswith(prefix))
        elif part in known_classes:
            matched.append(part)
        else:
            raise FormulaError(f"gl_class pattern {part!r} matches no known canonical class")
    return matched


def find_gl_class_patterns(formula: str) -> list[str]:
    """Every gl_class(...) argument referenced in formula, e.g.
    'gl_class(asset.fixed_asset_gross) - gl_class(asset.accumulated_depreciation)'
    -> ['asset.fixed_asset_gross', 'asset.accumulated_depreciation']."""
    return _GL_CLASS_TERM.findall(formula)


def eval_gl_class_formula(formula: str, amounts: dict[str, Decimal], known_classes: list[str]) -> Decimal:
    """Evaluates a formula built purely from gl_class(...) terms combined
    with + and - (every leaf metric's formula in config/metrics/ takes this
    shape). amounts: {canonical_class: Decimal} of RAW amount_base sums as
    fetched from fact_gl_entry -- each is converted to its natural-positive
    magnitude (natural_positive, above) before the formula's own +/- is
    applied, so 'gl_class(gross) - gl_class(accumulated_depreciation)'
    computes the ordinary net-of-depreciation figure rather than double
    counting the contra balance. A class absent from `amounts` had zero net
    activity and contributes zero."""
    terms = re.findall(r"[+-]?\s*gl_class\([^)]+\)", formula)
    if not terms or re.sub(r"\s+", "", "".join(terms)) != re.sub(r"\s+", "", formula):
        raise FormulaError(f"not a pure gl_class(...) +/- expression: {formula!r}")

    total = Decimal("0")
    for term in terms:
        term = term.strip()
        sign = Decimal("-1") if term.startswith("-") else Decimal("1")
        pattern = _GL_CLASS_TERM.search(term).group(1)
        for cls in match_gl_classes(pattern, known_classes):
            total += sign * natural_positive(cls, amounts.get(cls, Decimal("0")))
    return total


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


def _eval_ast(node: ast.AST, values: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise FormulaError(f"formula references {node.id!r}, which was not supplied as a dependency value")
        return values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_ast(node.operand, values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval_ast(node.left, values)
        right = _eval_ast(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise DivideByZero()
            return left / right
    raise FormulaError(f"unsupported formula syntax: {ast.dump(node)}")


def eval_metric_formula(formula: str, values: dict[str, Decimal]) -> Decimal:
    """formula: e.g. 'metric.net_revenue - metric.cogs',
    'metric.gross_profit / metric.net_revenue'. values: {metric_id: Decimal}
    of already-compiled dependency results, one entry per `metric.X` token
    the formula references."""
    python_expr = re.sub(r"metric\.([a-z0-9_]+)", r"\1", formula)
    try:
        tree = ast.parse(python_expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"could not parse formula {formula!r}: {e}") from e
    try:
        return _eval_ast(tree, values)
    except (InvalidOperation, DivisionByZero):
        raise DivideByZero()
