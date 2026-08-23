"""The fictional consumer brand's profile.

Per corpus/11 section 2.3: "Twelve months, multi-channel, with marketplace
commission, returns arriving in a later period than the sale, and an order
file that does not tie exactly to the books." Channels follow D-046's frozen
taxonomy (corpus/00): own website, marketplace (per marketplace), quick
commerce (per platform), owned retail, distributor.
"""
from datetime import date
from decimal import Decimal

COMPANY_NAME = "SYNTHETIC Brightleaf Consumer Brands Pvt Ltd"
GST_RATE = Decimal("0.18")
FISCAL_START = date(2025, 4, 1)
N_MONTHS = 12
ANNUAL_GMV = Decimal("1000000000")  # ~INR 100 Cr GMV across all channels

# (channel, channel_sub, revenue_model) -- D-061: marketplace vs buyout are
# distinct models, not one with a switch.
CHANNELS = [
    ("Own Website", "brightleaf.in", "buyout"),
    ("Marketplace - Amazon", "SELLER-IN-01", "marketplace"),
    ("Marketplace - Flipkart", "SELLER-FK-02", "marketplace"),
    ("Quick Commerce - Blinkit", "DARKSTORE-04", "buyout"),
    ("Owned Retail - Store1", "STORE-DEL-01", "buyout"),
]
