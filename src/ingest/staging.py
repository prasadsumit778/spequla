"""Typed staging for the trial balance, chart of accounts and general ledger
templates from corpus/01 -- the three streams named in the sprint 1 story.

Implements corpus/04 section 5 ("staging: typed, currency-converted,
deduplicated on row_hash") and the validity checks from corpus/09 section 2.2
that apply at this layer: a row failing structural validity is quarantined,
not silently coerced or dropped, per "Real MIS files carry live errors.
Validity check must quarantine rather than coerce to zero" (corpus/11
section 2.2, defect 11).

Money is Decimal, never float, per CLAUDE.md section 8.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from src.ingest.hashing import (
    BANK_ROW_HASH_FIELDS,
    CHANNEL_ORDER_ROW_HASH_FIELDS,
    PRODUCTION_OUTPUT_ROW_HASH_FIELDS,
    STORE_MASTER_ROW_HASH_FIELDS,
    compute_row_hash,
)
from src.ingest.templates import BANK, COA, CONSUMER_SALES, GL, MFG_PRODUCTION, STORE_MASTER, TB, Template
from src.ingest.xlsx import extract_template, looks_like_legacy_xls, looks_like_xlsx

PLAUSIBLE_DATE_MIN = date(1990, 1, 1)


@dataclass
class QuarantinedRow:
    row_index: int
    raw: dict
    reason: str


@dataclass
class StagingResult:
    valid_rows: list[dict] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)
    schema_hash: bytes = b""


def _read_csv(raw_bytes: bytes) -> tuple[list[str], list[dict]]:
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    header = reader.fieldnames or []
    return header, rows


def _read_tabular(raw_bytes: bytes, template: Template) -> tuple[list[str], list[dict]]:
    """Read one of corpus/01's templates from CSV or .xlsx bytes.

    corpus/02 section 3 P0 #1 is "Excel and CSV against the templates in file
    01". The format is decided by the bytes themselves, not by the file name,
    because a browser upload's name is user-supplied and a mislabelled
    extension must not change how a financial file is parsed.

    Both paths return the same (header, rows) shape, so the schema hash a
    caller computes is identical for a template supplied either way.
    """
    if looks_like_xlsx(raw_bytes) or looks_like_legacy_xls(raw_bytes):
        return extract_template(raw_bytes, list(template.columns))
    return _read_csv(raw_bytes)


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return Decimal("0")
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None  # signals an unparseable numeric cell, e.g. '#DIV/0!'


def _parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _plausible_date(d: date, today: date) -> bool:
    return PLAUSIBLE_DATE_MIN <= d <= today + timedelta(days=1)


def stage_coa(raw_bytes: bytes) -> StagingResult:
    from src.ingest.landing import schema_hash as compute_schema_hash
    header, rows = _read_tabular(raw_bytes, COA)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    for i, row in enumerate(rows):
        opening = _parse_decimal(row.get("opening_balance"))
        if opening is None:
            result.quarantined.append(QuarantinedRow(i, row, "opening_balance is not a valid number"))
            continue
        if not (row.get("account_code") or row.get("account_name")):
            result.quarantined.append(QuarantinedRow(i, row, "no account_code and no account_name"))
            continue
        result.valid_rows.append({
            "account_code": (row.get("account_code") or "").strip(),
            "account_name": row["account_name"],  # verbatim, never cleaned, per corpus/04 section 3.2
            "parent_group": row.get("parent_group") or None,
            "account_type": row.get("account_type") or None,
            "opening_balance": opening,
            "opening_dr_cr": row.get("opening_dr_cr") or None,
            "cost_centre": row.get("cost_centre") or None,
            "is_active": (row.get("is_active") or "Yes").strip().lower() != "no",
        })
    return result


def stage_tb(raw_bytes: bytes) -> StagingResult:
    from src.ingest.landing import schema_hash as compute_schema_hash
    header, rows = _read_tabular(raw_bytes, TB)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    for i, row in enumerate(rows):
        period_end = _parse_date(row.get("period_end"))
        if period_end is None:
            result.quarantined.append(QuarantinedRow(i, row, "period_end is missing or not YYYY-MM-DD"))
            continue
        parsed = {k: _parse_decimal(row.get(k)) for k in
                    ("opening_balance", "debit_movement", "credit_movement", "closing_balance")}
        bad = [k for k, v in parsed.items() if v is None]
        if bad:
            result.quarantined.append(QuarantinedRow(i, row, f"unparseable numeric field(s): {bad}"))
            continue
        result.valid_rows.append({
            "period_end": period_end, "account_code": (row.get("account_code") or "").strip(),
            "account_name": row.get("account_name"), **parsed,
        })
    return result


def stage_gl(raw_bytes: bytes, today: date | None = None) -> StagingResult:
    """Returns typed, validated GL lines plus a row_hash on each, deduplicated
    within this call on (voucher_no, line_no, row_hash). Deduplication ACROSS
    load runs (the same file uploaded twice) happens at canonical-write time
    against fact_gl_entry.row_hash, per corpus/09 section 2.3 -- this function
    only guarantees the batch it is given contains no internal duplicates."""
    from src.ingest.landing import schema_hash as compute_schema_hash
    today = today or date.today()
    header, rows = _read_tabular(raw_bytes, GL)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows):
        voucher_date = _parse_date(row.get("voucher_date"))
        if voucher_date is None:
            result.quarantined.append(QuarantinedRow(i, row, "voucher_date is missing or not YYYY-MM-DD"))
            continue
        if not _plausible_date(voucher_date, today):
            result.quarantined.append(QuarantinedRow(i, row, "voucher_date outside the plausible range"))
            continue
        entry_date = _parse_date(row.get("entry_date")) or voucher_date

        debit = _parse_decimal(row.get("debit"))
        credit = _parse_decimal(row.get("credit"))
        if debit is None or credit is None:
            result.quarantined.append(QuarantinedRow(i, row, "debit or credit is not a valid number"))
            continue
        if debit > 0 and credit > 0:
            result.quarantined.append(QuarantinedRow(i, row, "both debit and credit populated on one line"))
            continue
        if not row.get("account_code") and not row.get("account_name"):
            result.quarantined.append(QuarantinedRow(i, row, "no account_code and no account_name"))
            continue
        try:
            line_no = int(row.get("line_no") or 0)
        except ValueError:
            result.quarantined.append(QuarantinedRow(i, row, "line_no is not an integer"))
            continue

        amount_base = debit if debit > 0 else -credit  # Dr positive, Cr negative, per corpus/03 section 1
        staged = {
            "voucher_no": row["voucher_no"], "voucher_type": row["voucher_type"],
            "voucher_date": voucher_date, "entry_date": entry_date, "line_no": line_no,
            "account_code": (row.get("account_code") or "").strip(), "account_name": row.get("account_name"),
            "debit": debit, "credit": credit, "amount_base": amount_base,
            "amount_txn": amount_base, "currency_code": "INR", "fx_rate": Decimal("1"),
            "fx_rate_source": "GL template carries no currency field; single-currency INR assumed",
            "narration": row.get("narration") or None, "cost_centre": row.get("cost_centre") or None,
            "party_name": row.get("party_name") or None,
            "is_cancelled": (row.get("is_cancelled") or "No").strip().lower() == "yes",
            "is_opening_balance": False,
        }
        staged["row_hash"] = compute_row_hash({
            "voucher_no": staged["voucher_no"], "voucher_type": staged["voucher_type"],
            "voucher_date": staged["voucher_date"].isoformat(), "entry_date": staged["entry_date"].isoformat(),
            "line_no": staged["line_no"], "account_code": staged["account_code"],
            "debit": str(staged["debit"]), "credit": str(staged["credit"]),
            "narration": staged["narration"], "cost_centre": staged["cost_centre"],
            "party_name": staged["party_name"], "is_cancelled": staged["is_cancelled"],
        })

        dedup_key = (staged["voucher_no"], staged["line_no"], staged["row_hash"])
        if dedup_key in seen_keys:
            result.quarantined.append(QuarantinedRow(i, row, "duplicate voucher_no/line_no/content within this file"))
            continue
        seen_keys.add(dedup_key)
        result.valid_rows.append(staged)

    return result


def stage_bank(raw_bytes: bytes, today: date | None = None) -> StagingResult:
    """corpus/01's Bank template. amount_base: money in positive, money out
    negative (fact_bank_txn's own documented sign convention -- bank lines
    have no natural Dr/Cr side the way GL lines do)."""
    from src.ingest.landing import schema_hash as compute_schema_hash
    today = today or date.today()
    header, rows = _read_tabular(raw_bytes, BANK)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows):
        txn_date = _parse_date(row.get("txn_date"))
        if txn_date is None:
            result.quarantined.append(QuarantinedRow(i, row, "txn_date is missing or not YYYY-MM-DD"))
            continue
        if not _plausible_date(txn_date, today):
            result.quarantined.append(QuarantinedRow(i, row, "txn_date outside the plausible range"))
            continue
        value_date = _parse_date(row.get("value_date"))  # optional per corpus/01

        debit = _parse_decimal(row.get("debit"))
        credit = _parse_decimal(row.get("credit"))
        running_balance = _parse_decimal(row.get("running_balance"))
        if debit is None or credit is None or running_balance is None:
            result.quarantined.append(QuarantinedRow(i, row, "debit, credit or running_balance is not a valid number"))
            continue
        if debit > 0 and credit > 0:
            result.quarantined.append(QuarantinedRow(i, row, "both debit and credit populated on one line"))
            continue
        if not row.get("bank_account_ref"):
            result.quarantined.append(QuarantinedRow(i, row, "no bank_account_ref"))
            continue
        if not row.get("description"):
            result.quarantined.append(QuarantinedRow(i, row, "no description"))
            continue

        staged = {
            "bank_account_ref": row["bank_account_ref"].strip(),
            "event_date": txn_date, "value_date": value_date, "entry_date": txn_date,
            "description": row["description"], "reference": row.get("reference") or None,
            "debit": debit, "credit": credit, "amount_base": credit - debit,
            "running_balance_reported": running_balance,
        }
        staged["row_hash"] = compute_row_hash({
            "bank_account_ref": staged["bank_account_ref"], "txn_date": staged["event_date"].isoformat(),
            "value_date": staged["value_date"].isoformat() if staged["value_date"] else "",
            "description": staged["description"], "reference": staged["reference"],
            "debit": str(staged["debit"]), "credit": str(staged["credit"]),
            "running_balance": str(staged["running_balance_reported"]),
        }, fields=BANK_ROW_HASH_FIELDS)

        dedup_key = (staged["bank_account_ref"], staged["row_hash"])
        if dedup_key in seen_keys:
            result.quarantined.append(QuarantinedRow(i, row, "duplicate bank line within this file"))
            continue
        seen_keys.add(dedup_key)
        result.valid_rows.append(staged)

    return result


def stage_channel_order(raw_bytes: bytes, today: date | None = None) -> StagingResult:
    """Consumer Sales / channel order line, corpus/04 section 3.5. The
    source template carries no line_no column (each row is already one
    order line in this data source) -- line_no is assigned 1 for every row
    at staging, a shape fact rather than a business value, so
    source_record_id (order_id#line_no) stays consistent with the DDL's own
    (order_id, line_no) grain even though no template row ever supplies a
    second line for one order_id today."""
    from src.ingest.landing import schema_hash as compute_schema_hash
    today = today or date.today()
    header, rows = _read_tabular(raw_bytes, CONSUMER_SALES)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows):
        order_date = _parse_date(row.get("order_date"))
        if order_date is None:
            result.quarantined.append(QuarantinedRow(i, row, "order_date is missing or not YYYY-MM-DD"))
            continue
        if not _plausible_date(order_date, today):
            result.quarantined.append(QuarantinedRow(i, row, "order_date outside the plausible range"))
            continue
        if not row.get("order_id"):
            result.quarantined.append(QuarantinedRow(i, row, "no order_id"))
            continue
        if not row.get("item_code"):
            result.quarantined.append(QuarantinedRow(i, row, "no item_code"))
            continue
        if not row.get("channel"):
            result.quarantined.append(QuarantinedRow(i, row, "no channel"))
            continue

        numeric_fields = ("quantity", "gross_amount", "discount_amount", "net_amount", "shipping_charged",
                            "commission_amount", "shipping_cost", "payment_fee", "commission_earned",
                            "advertising_earned", "platform_fee_earned")
        parsed = {k: _parse_decimal(row.get(k)) for k in numeric_fields}
        bad = [k for k, v in parsed.items() if v is None]
        if bad:
            result.quarantined.append(QuarantinedRow(i, row, f"unparseable numeric field(s): {bad}"))
            continue

        revenue_model = (row.get("revenue_model") or "buyout").strip().lower()
        if revenue_model not in ("marketplace", "buyout"):
            result.quarantined.append(QuarantinedRow(i, row, f"revenue_model {revenue_model!r} is not "
                                                                 f"'marketplace' or 'buyout' -- D-061"))
            continue

        return_flag = (row.get("return_flag") or "No").strip().lower() == "yes"
        return_date = _parse_date(row.get("return_date")) if return_flag else None

        line_no = 1
        staged = {
            "order_id": row["order_id"], "line_no": line_no, "event_date": order_date,
            "channel": row["channel"], "channel_sub": row.get("channel_sub") or None,
            "customer_code": row.get("customer_code") or None, "item_code": row["item_code"],
            "item_name": row.get("item_name") or None,
            "quantity": parsed["quantity"], "gross_amount": parsed["gross_amount"],
            "discount_amount": parsed["discount_amount"], "net_amount": parsed["net_amount"],
            "shipping_charged": parsed["shipping_charged"], "commission_amount": parsed["commission_amount"],
            "shipping_cost": parsed["shipping_cost"], "payment_fee": parsed["payment_fee"],
            "revenue_model": revenue_model, "order_type": row.get("order_type") or None,
            "commission_earned": parsed["commission_earned"], "advertising_earned": parsed["advertising_earned"],
            "platform_fee_earned": parsed["platform_fee_earned"],
            "is_returned": return_flag, "return_date": return_date, "return_reason": row.get("return_reason") or None,
            "settlement_date": _parse_date(row.get("settlement_date")),
        }
        staged["row_hash"] = compute_row_hash({
            "order_id": staged["order_id"], "order_date": order_date.isoformat(), "channel": staged["channel"],
            "channel_sub": staged["channel_sub"], "customer_code": staged["customer_code"],
            "item_code": staged["item_code"], "quantity": str(staged["quantity"]),
            "gross_amount": str(staged["gross_amount"]), "discount_amount": str(staged["discount_amount"]),
            "net_amount": str(staged["net_amount"]), "shipping_charged": str(staged["shipping_charged"]),
            "commission_amount": str(staged["commission_amount"]), "shipping_cost": str(staged["shipping_cost"]),
            "payment_fee": str(staged["payment_fee"]), "return_flag": staged["is_returned"],
            "return_date": return_date.isoformat() if return_date else "",
            "return_reason": staged["return_reason"], "revenue_model": staged["revenue_model"],
            "order_type": staged["order_type"], "commission_earned": str(staged["commission_earned"]),
            "advertising_earned": str(staged["advertising_earned"]),
            "platform_fee_earned": str(staged["platform_fee_earned"]),
        }, fields=CHANNEL_ORDER_ROW_HASH_FIELDS)

        dedup_key = (staged["order_id"], staged["line_no"], staged["row_hash"])
        if dedup_key in seen_keys:
            result.quarantined.append(QuarantinedRow(i, row, "duplicate order_id/line_no/content within this file"))
            continue
        seen_keys.add(dedup_key)
        result.valid_rows.append(staged)

    return result


def stage_store_master(raw_bytes: bytes) -> StagingResult:
    """Store Master, corpus/04 section 3.10. One row per store; store_code is
    the source_record_id that Consumer Sales' channel_sub references for a
    store-format order row (corpus/13 section 2). Dimension-only, no fact
    write -- same shape as stage_coa."""
    from src.ingest.landing import schema_hash as compute_schema_hash
    header, rows = _read_tabular(raw_bytes, STORE_MASTER)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    seen_codes: set[str] = set()

    for i, row in enumerate(rows):
        if not row.get("store_code"):
            result.quarantined.append(QuarantinedRow(i, row, "no store_code"))
            continue
        if not row.get("store_name"):
            result.quarantined.append(QuarantinedRow(i, row, "no store_name"))
            continue
        opening_date = _parse_date(row.get("opening_date"))
        if opening_date is None:
            result.quarantined.append(QuarantinedRow(i, row, "opening_date is missing or not YYYY-MM-DD"))
            continue
        closure_date = _parse_date(row.get("closure_date")) if row.get("closure_date") else None
        area_sqft = _parse_decimal(row.get("area_sqft")) if row.get("area_sqft") else None
        if row.get("area_sqft") and area_sqft is None:
            result.quarantined.append(QuarantinedRow(i, row, "area_sqft is not a valid number"))
            continue

        store_code = row["store_code"].strip()
        if store_code in seen_codes:
            result.quarantined.append(QuarantinedRow(i, row, f"duplicate store_code {store_code!r} within this file"))
            continue
        seen_codes.add(store_code)

        staged = {
            "store_code": store_code, "store_name": row["store_name"],
            "store_format": (row.get("store_format") or "").strip().upper() or None,
            "city": row.get("city") or None, "state": row.get("state") or None,
            "site_type": row.get("site_type") or None, "area_sqft": area_sqft,
            "opening_date": opening_date, "closure_date": closure_date,
            "status": (row.get("status") or "active").strip().lower(),
        }
        staged["row_hash"] = compute_row_hash({
            **staged, "opening_date": opening_date.isoformat(),
            "closure_date": closure_date.isoformat() if closure_date else "",
            "area_sqft": str(area_sqft) if area_sqft is not None else "",
        }, fields=STORE_MASTER_ROW_HASH_FIELDS)
        result.valid_rows.append(staged)

    return result


def stage_mfg_production(raw_bytes: bytes, today: date | None = None) -> StagingResult:
    """MFG Production, corpus/04 section 3.6. period column is a month-end
    date in this template (see synthetic/manufacturer/write.py's MFG_FIELDS);
    event_date is that month-end, period_key derived from it."""
    from src.ingest.landing import schema_hash as compute_schema_hash
    today = today or date.today()
    header, rows = _read_tabular(raw_bytes, MFG_PRODUCTION)
    result = StagingResult(schema_hash=compute_schema_hash(header))
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows):
        event_date = _parse_date(row.get("period"))
        if event_date is None:
            result.quarantined.append(QuarantinedRow(i, row, "period is missing or not YYYY-MM-DD"))
            continue
        if not _plausible_date(event_date, today):
            result.quarantined.append(QuarantinedRow(i, row, "period outside the plausible range"))
            continue
        if not row.get("item_code"):
            result.quarantined.append(QuarantinedRow(i, row, "no item_code"))
            continue
        if not row.get("plant_or_line"):
            result.quarantined.append(QuarantinedRow(i, row, "no plant_or_line"))
            continue
        if not row.get("uom"):
            result.quarantined.append(QuarantinedRow(i, row, "no uom"))
            continue

        numeric_fields = ("qty_produced", "qty_rejected", "input_qty", "available_hours",
                            "running_hours", "power_units")
        parsed = {k: _parse_decimal(row.get(k)) for k in numeric_fields}
        bad = [k for k, v in parsed.items() if v is None]
        if bad:
            result.quarantined.append(QuarantinedRow(i, row, f"unparseable numeric field(s): {bad}"))
            continue

        staged = {
            "event_date": event_date, "period_key": f"{event_date.year:04d}-{event_date.month:02d}",
            "plant_or_line": row["plant_or_line"], "item_code": row["item_code"],
            "item_name": row.get("item_name") or None,
            "qty_produced": parsed["qty_produced"], "qty_rejected": parsed["qty_rejected"],
            "uom": row["uom"].strip(), "input_qty": parsed["input_qty"], "input_uom": row.get("input_uom") or None,
            "available_hours": parsed["available_hours"], "running_hours": parsed["running_hours"],
            "power_units": parsed["power_units"],
        }
        staged["row_hash"] = compute_row_hash({
            "period": event_date.isoformat(), "plant_or_line": staged["plant_or_line"],
            "item_code": staged["item_code"], "qty_produced": str(staged["qty_produced"]),
            "qty_rejected": str(staged["qty_rejected"]), "uom": staged["uom"],
            "input_qty": str(staged["input_qty"]) if staged["input_qty"] is not None else "",
            "input_uom": staged["input_uom"],
            "available_hours": str(staged["available_hours"]) if staged["available_hours"] is not None else "",
            "running_hours": str(staged["running_hours"]) if staged["running_hours"] is not None else "",
            "power_units": str(staged["power_units"]) if staged["power_units"] is not None else "",
        }, fields=PRODUCTION_OUTPUT_ROW_HASH_FIELDS)

        dedup_key = (staged["period_key"], staged["plant_or_line"], staged["item_code"], staged["row_hash"])
        if dedup_key in seen_keys:
            result.quarantined.append(QuarantinedRow(i, row, "duplicate period/plant_or_line/item_code within this file"))
            continue
        seen_keys.add(dedup_key)
        result.valid_rows.append(staged)

    return result
