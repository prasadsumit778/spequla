"""Generate config/decisions.yml from corpus/00_SPEQULA_OPEN_DECISIONS.md.

Implements: corpus/12 Sprint 0 item 1 ("Generate /config/decisions.yml from /corpus/00,
one entry per decision with id, status, resolution text where resolved, and the files
it governs"). Transcription only -- this script does not resolve, infer, or default
anything the corpus itself does not state.
"""
import re
import sys
from pathlib import Path

import yaml

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "00_SPEQULA_OPEN_DECISIONS.md"
OUT = Path(__file__).resolve().parent.parent / "config" / "decisions.yml"

ID_RE = re.compile(r"^\*{0,2}(~~)?\*{0,2}(D-\d{3}|V-\d{3})\*{0,2}(~~)?\*{0,2}$")


def parse_markdown_tables(text: str):
    """Yield (header_cells, row_cells) for every pipe-table row in the document."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(row) == len(header):
                    yield header, row
                i += 1
        else:
            i += 1


def clean(cell: str) -> str:
    # Strip markdown bold/strike, collapse footnote-style asterisks.
    cell = cell.replace("**", "").replace("~~", "")
    return cell.strip()


def extract_id(cell: str):
    m = ID_RE.match(cell.strip())
    return m.group(2) if m else None


def main():
    text = CORPUS.read_text()
    records: dict[str, dict] = {}

    for header, row in parse_markdown_tables(text):
        cells = dict(zip(header, row))
        id_col = next((h for h in header if h.upper() == "ID"), None)
        if not id_col:
            continue
        did = extract_id(cells[id_col])
        if not did:
            continue
        rec = records.setdefault(did, {"id": did, "type": "decision" if did.startswith("D-") else "verify"})
        for key in ("Decision", "Item", "Options", "Suggested", "Why it matters", "Why it stays open",
                    "Why it is open", "Blocks", "Resolution", "Outcome", "Owner"):
            if key in cells and clean(cells[key]):
                rec[key] = clean(cells[key])

    # Section 2b RESOLVED table gives the authoritative resolution text and marks status.
    resolved_ids = set()
    for header, row in parse_markdown_tables(text):
        if header[:2] == ["ID", "Resolution"]:
            cells = dict(zip(header, row))
            did = extract_id(cells["ID"])
            if did:
                records.setdefault(did, {"id": did, "type": "decision"})
                records[did]["Resolution"] = clean(cells["Resolution"])
                resolved_ids.add(did)

    # "Still open: 12" table.
    open_ids = set()
    for header, row in parse_markdown_tables(text):
        if header[:2] == ["ID", "Why it stays open"]:
            cells = dict(zip(header, row))
            did = extract_id(cells["ID"])
            if did:
                open_ids.add(did)

    # VERIFY closed table gives Outcome text and marks status.
    verify_closed = {}
    for header, row in parse_markdown_tables(text):
        if header[:2] == ["ID", "Outcome"]:
            cells = dict(zip(header, row))
            did = extract_id(cells["ID"])
            if did:
                verify_closed[did] = clean(cells["Outcome"])

    out = []
    for did in sorted(records, key=lambda x: (x[0], int(x[2:]))):
        rec = records[did]
        governs = []
        if "Blocks" in rec:
            governs = [g.strip() for g in re.split(r"[,|]", rec["Blocks"]) if g.strip()]

        if did in resolved_ids:
            status = "resolved"
            resolution = rec.get("Resolution")
        elif did in verify_closed and "still open" not in verify_closed[did].lower():
            status = "resolved"
            resolution = verify_closed[did]
        elif did in verify_closed:
            # Listed in the "VERIFY closed" table but its own outcome text says it
            # remains open (e.g. V-003: "no longer blocking" is not "resolved").
            status = "open"
            resolution = None
            rec["_note"] = verify_closed[did]
        elif did in open_ids:
            status = "open"
            resolution = None
        elif did.startswith("V-"):
            # VERIFY items not in the closed table are still open.
            status = "open"
            resolution = None
        else:
            # Decision resolved via "second pass" / "SECOND PASS" acceptance table,
            # or already carries a Resolution field directly from a per-decision row
            # (e.g. D-026, resolved inline in section F).
            if "Resolution" in rec:
                status = "resolved"
                resolution = rec["Resolution"]
            else:
                status = "open"
                resolution = None

        out.append({
            "id": did,
            "type": rec["type"],
            "status": status,
            "resolution": resolution,
            "note": rec.get("_note"),
            "label": rec.get("Decision") or rec.get("Item"),
            "governs": governs,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("# Generated from corpus/00_SPEQULA_OPEN_DECISIONS.md. Do not hand-edit.\n")
        f.write("# Regenerate with scripts/gen_decisions_yml.py whenever the corpus changes.\n")
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=100)

    n_decision = sum(1 for r in out if r["type"] == "decision")
    n_verify = sum(1 for r in out if r["type"] == "verify")
    n_open = sum(1 for r in out if r["status"] == "open")
    print(f"Wrote {len(out)} entries ({n_decision} decisions, {n_verify} verify) to {OUT}")
    print(f"  open: {n_open}, resolved: {len(out) - n_open}")
    open_d = sorted(r["id"] for r in out if r["status"] == "open" and r["type"] == "decision")
    open_v = sorted(r["id"] for r in out if r["status"] == "open" and r["type"] == "verify")
    print(f"  open decisions ({len(open_d)}): {', '.join(open_d)}")
    print(f"  open verify ({len(open_v)}): {', '.join(open_v)}")


if __name__ == "__main__":
    sys.exit(main())
