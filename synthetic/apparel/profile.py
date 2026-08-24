"""The fictional omnichannel ethnic-wear retailer's profile.

Store-cohort mechanics, channel growth ranges, cost growth rates, category
mix and margin trajectory are all derived from patterns and realistic
magnitudes in a real apparel-retail financial model reviewed for corpus/13 --
store formats (COCO/COFO/FOCO/FOFO), gestation-period store vintaging,
channel-tier online growth, price-band/occasion product cuts, personnel/rent
growth rates, margin expansion. Every number below is this fictional
company's own invented figure, not a transcription of the source model's
actual cells -- see corpus/13 section 1 for the mechanics this profile
exercises and why.

Per corpus/00, several of these (like D-001/D-002/D-012 etc. for the other
profiles) are properties of a specific company's own books, not a SPEQULA
product default -- this is that company's one concrete, internally
consistent set of answers, exactly as a real company would have its own
before the accounting policy conversation in corpus/00 section 3.
"""
from datetime import date
from decimal import Decimal

COMPANY_NAME = "SYNTHETIC Malhar Ethnic Apparel Pvt Ltd"
GST_RATE = Decimal("0.18")
FISCAL_START = date(2021, 4, 1)  # FY22 start
N_MONTHS = 60  # FY22 through FY26, five years of actuals

STORE_FORMATS = ["COCO", "COFO", "FOCO", "FOFO"]

# Stores already open and mature at FISCAL_START (opening_date pre-dates the
# history window). No FOFO legacy stores -- that format is newer to the
# expansion plan, per the store pipeline below.
LEGACY_STORE_COUNT = {"COCO": 5, "COFO": 3, "FOCO": 2, "FOFO": 0}

# New stores opened PER FISCAL YEAR (index 0 = FY22 .. index 4 = FY26), by format.
STORE_ADDITIONS_BY_YEAR = {
    "COCO": [3, 4, 4, 5, 5],
    "COFO": [2, 3, 4, 4, 5],
    "FOCO": [1, 2, 2, 3, 3],
    "FOFO": [1, 1, 2, 2, 3],
}

# A new store's expected FULL run-rate annual sales once mature (month 25+).
YEAR1_AVG_ANNUAL_SALES_INR = {
    "COCO": Decimal("21000000"), "COFO": Decimal("18500000"),
    "FOCO": Decimal("16000000"), "FOFO": Decimal("13500000"),
}
# Two-year gestation: months 1-12 at 55% of run-rate, 13-24 at 80%, then full.
GESTATION_RAMP = [(12, Decimal("0.55")), (24, Decimal("0.80"))]
EXISTING_STORE_PRICE_GROWTH_YOY = Decimal("0.04")
EXISTING_STORE_CUSTOMER_GROWTH_YOY = Decimal("0.025")

# Who bears which store-level cost, by format -- ownership drives rent,
# operation drives personnel, and a franchise party anywhere in the
# ownership/operation split earns a commission. COCO: company owns and
# operates, bears both, no commission. COFO: company owns (bears rent) but a
# franchisee operates (company keeps a reduced support-personnel cost, pays
# commission). FOCO: a franchisee owns the premises (company does not bear
# rent) but the company operates it (bears personnel), still pays a
# commission for the franchise relationship. FOFO: franchisee owns and
# operates -- company bears neither rent nor personnel, only commission.
STORE_RENT_SHARE = {"COCO": Decimal("1.0"), "COFO": Decimal("1.0"), "FOCO": Decimal("0"), "FOFO": Decimal("0")}
STORE_PERSONNEL_SHARE = {"COCO": Decimal("1.0"), "COFO": Decimal("0.5"), "FOCO": Decimal("1.0"), "FOFO": Decimal("0")}
FRANCHISE_COMMISSION_APPLIES = {"COCO": False, "COFO": True, "FOCO": True, "FOFO": True}
FRANCHISE_COMMISSION_RATE = Decimal("0.10")  # of that format's monthly store sales

# Per-store-per-year average cost at a mature store, before YoY growth is applied.
STORE_RENT_PER_STORE_ANNUAL = Decimal("3200000")
STORE_PERSONNEL_PER_STORE_ANNUAL = Decimal("4800000")
STORE_RENT_GROWTH_YOY = Decimal("0.06")
STORE_PERSONNEL_GROWTH_YOY = Decimal("0.07")

CITIES = [  # (city, state, tier) -- invented spread across metro/tier-1/tier-2 India
    ("Mumbai", "Maharashtra", "metro"), ("Delhi", "Delhi", "metro"), ("Bengaluru", "Karnataka", "metro"),
    ("Pune", "Maharashtra", "tier1"), ("Ahmedabad", "Gujarat", "tier1"), ("Jaipur", "Rajasthan", "tier1"),
    ("Lucknow", "Uttar Pradesh", "tier1"), ("Indore", "Madhya Pradesh", "tier2"), ("Surat", "Gujarat", "tier2"),
    ("Nagpur", "Maharashtra", "tier2"), ("Bhopal", "Madhya Pradesh", "tier2"), ("Coimbatore", "Tamil Nadu", "tier2"),
]
SITE_TYPES = ["mall", "high_street"]
AREA_SQFT_RANGE = (650, 2200)

# Online channel tiers: (display_name, channel_sub, tier).
ONLINE_CHANNELS = [
    ("Marketplace - Myntra", "MYNTRA-01", "tier1"),
    ("Marketplace - Ajio", "AJIO-01", "tier1"),
    ("Marketplace - Nykaa", "NYKAA-01", "tier2"),
    ("Marketplace - Flipkart", "FLIPKART-01", "tier2"),
    ("Own Website", "malhar.in", "own_site"),
]
ONLINE_ORDERS_GROWTH_YOY = {"tier1": Decimal("0.40"), "tier2": Decimal("0.28"), "own_site": Decimal("0.22")}
ONLINE_PRICE_GROWTH_YOY = Decimal("0.025")
ONLINE_STARTING_MONTHLY_ORDERS = {"tier1": 900, "tier2": 500, "own_site": 700}
ONLINE_STARTING_AOV = Decimal("1450")
ONLINE_COMMISSION_RATE = Decimal("0.16")  # marketplace channels only
ONLINE_AD_SPEND_PCT_OF_SALES = Decimal("0.075")

# Product categories: (name, occasion_type, price_band). Garment-type and
# price-band vocabulary standard across Indian apparel retail, not brand IP.
CATEGORIES = [
    ("Saree", "occasion_fusion", "d.2001-2500"),
    ("Salwar Suit", "casual", "b.1001-1500"),
    ("Kurta", "casual", "b.1001-1500"),
    ("Unstitch", "casual", "c.1501-2000"),
    ("Kurta Set", "occasion_fusion", "c.1501-2000"),
    ("Blouse", "evening", "b.1001-1500"),
    ("Dress", "evening", "d.2001-2500"),
    ("Tunic", "casual", "a.<1000"),
    ("Others", "casual", "a.<1000"),
]
# Category mix drifts linearly from START to TARGET across the history window
# (a real trend to detect, not a flat share held constant for five years).
CATEGORY_MIX_START = {
    "Saree": Decimal("0.28"), "Salwar Suit": Decimal("0.14"), "Kurta": Decimal("0.23"),
    "Unstitch": Decimal("0.09"), "Kurta Set": Decimal("0.06"), "Blouse": Decimal("0.02"),
    "Dress": Decimal("0.01"), "Tunic": Decimal("0.03"), "Others": Decimal("0.14"),
}
CATEGORY_MIX_TARGET = {
    "Saree": Decimal("0.16"), "Salwar Suit": Decimal("0.25"), "Kurta": Decimal("0.17"),
    "Unstitch": Decimal("0.10"), "Kurta Set": Decimal("0.05"), "Blouse": Decimal("0.05"),
    "Dress": Decimal("0.05"), "Tunic": Decimal("0.03"), "Others": Decimal("0.14"),
}

HO_COST_GROWTH_YOY = Decimal("0.075")
HO_EMPLOYEE_COST_START_ANNUAL = Decimal("28000000")
WAREHOUSE_COST_START_ANNUAL = Decimal("11000000")
ADMIN_COST_START_ANNUAL = Decimal("9000000")

# Gross margin expands linearly across the history (price increases, better
# vendor terms, higher full-price sell-through), not held flat.
GP_MARGIN_START = Decimal("0.52")
GP_MARGIN_END = Decimal("0.60")
DISCOUNT_RATE = Decimal("0.08")  # applied to gross before GST, both channels
