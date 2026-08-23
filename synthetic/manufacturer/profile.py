"""The fictional manufacturer's accounting policy choices.

Per corpus/00, decisions D-001, D-002, D-012, D-015, D-016, D-017, D-018,
D-041, D-042 are deliberately left open in the corpus -- they are properties
of a specific company's own books, "read from the books," not invented by
SPEQULA. A synthetic company needs one concrete, internally consistent set of
answers to exist at all, exactly as a real company would have its own answers
before the accounting policy conversation in corpus/00 section 3 uncovers
them. These are THIS FICTIONAL COMPANY's bookkeeping choices, not a SPEQULA
product default -- SPEQULA's own loader (src/config/loader.py) still treats
every one of these decisions as open and refuses to serve the metrics they
govern until a real accounting policy conversation resolves them per company.

  D-001 GST treatment              -> exclusive (sales ledgers booked net of GST)
  D-002 revenue recognition point  -> invoice date
  D-012 freight inward             -> expensed (not capitalised into inventory)
  D-015 power and fuel             -> COGS, via absorption
  D-016 direct labour              -> COGS, with a cost-centre split that DOES exist
  D-017 costing basis              -> standard costing, variance in COGS (so defect
                                       #13, absorption variance masking a margin
                                       fall, has somewhere to hide)
  D-018 inventory valuation        -> weighted average
  D-041 declared unit of measure   -> MT (metric tonnes) per product family
  D-042 capacity basis             -> practical capacity
"""
from datetime import date
from decimal import Decimal

COMPANY_NAME = "SYNTHETIC Ferrotech Industries Pvt Ltd"
GST_RATE = Decimal("0.18")
FISCAL_START = date(2023, 4, 1)  # FY24 April
N_MONTHS = 36                     # through March 2026 (FY24, FY25, FY26)
ANNUAL_REVENUE_Y1 = Decimal("1000000000")  # ~INR 100 Cr in year 1
YOY_GROWTH = Decimal("0.08")
GROSS_MARGIN_TARGET = Decimal("0.30")
OPEX_PCT_OF_REVENUE = Decimal("0.15")
