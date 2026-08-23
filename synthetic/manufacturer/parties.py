"""Customers, vendors and items for the synthetic manufacturer.

Per corpus/02 section 8, real customer/vendor names would be tokenised at
ingestion -- these synthetic names are themselves already fictional (never
real entities), consistent with corpus/11's "everything in it is invented."
"""
from __future__ import annotations

from dataclasses import dataclass

from synthetic.common import Rng

CUSTOMER_NAMES = [
    "Acme Traders Pvt Ltd", "Northern Steel Distributors", "Vishal Enterprises",
    "Coastal Metals Trading Co", "Bharat Fabricators", "Sunrise Industrial Supplies",
    "Gupta & Sons Hardware", "Metro Engineering Works", "Delta Infra Projects",
    "Sagar Steel Traders", "Prime Building Materials", "Kalyani Industrial Corp",
    "Everest Structurals Ltd", "Om Sai Traders", "Continental Metal Works",
    "Rajesh Steel Corporation", "Blue Ridge Fabrication", "National Pipe Distributors",
    "Star Engineering Co", "Ganesh Traders", "Silverline Industries",
    "Unity Steel Solutions", "Anand Metal Mart", "Vertex Construction Supplies",
    "Harmony Industrial Traders", "Crescent Steel Co", "Falcon Distributors",
    "Trinity Fabricators Pvt Ltd", "Meridian Metal Traders", "Apex Structural Works",
]

VENDOR_NAMES = [
    "Northern Steel Suppliers", "Bharat Alloys Ltd", "Zinc Corp of India",
    "Precision Packing Solutions", "Reliable Stores & Consumables",
    "Sunrise Freight Carriers", "Metro Logistics Pvt Ltd", "PowerGrid Distribution Co",
    "State Electricity Board", "Om Job Work Services", "Kalyani Castings Pvt Ltd",
    "National Coil Traders", "Standard Packing Industries", "Continental Freight Ltd",
    "Vishal Transport Co", "Ganesh Raw Materials", "Everest Alloys Pvt Ltd",
    "Delta Consumables Supply", "Rajesh Industrial Traders", "Blue Star Fasteners",
    "Silverline Ancillaries", "Unity Steel Raw Materials", "Anand Freight Services",
    "Vertex Industrial Supply", "Harmony Vendor Solutions",
]

ITEMS = [
    # (code, name, category, uom, family)
    ("SKU-4402", "MS Angle 50x50x5", "Structural Steel", "MT", "angle"),
    ("SKU-4415", "MS Angle 65x65x6", "Structural Steel", "MT", "angle"),
    ("SKU-5501", "MS Channel 100mm", "Structural Steel", "MT", "channel"),
    ("SKU-5520", "MS Channel 150mm", "Structural Steel", "MT", "channel"),
    ("SKU-6001", "GI Sheet 0.5mm", "Sheet Products", "MT", "gi_sheet"),
    ("SKU-6010", "GI Sheet 0.8mm", "Sheet Products", "MT", "gi_sheet"),
    ("SKU-6100", "CR Sheet 1.0mm", "Sheet Products", "MT", "cr_sheet"),
    ("SKU-7001", "MS Round Bar 12mm", "Bars", "MT", "round_bar"),
    ("SKU-7010", "MS Round Bar 16mm", "Bars", "MT", "round_bar"),
    ("SKU-8001", "MS Flat 40x5", "Flats", "MT", "flat"),
    ("SKU-8010", "MS Flat 50x6", "Flats", "MT", "flat"),
    ("SKU-9001", "Galvanised Wire 4mm", "Wire Products", "MT", "wire"),
]

RM_ITEMS = [
    ("RM-1001", "HR Coil 3mm", "Raw Material", "MT", "hr_coil"),
    ("RM-1002", "CR Coil 1mm", "Raw Material", "MT", "cr_coil"),
    ("RM-1003", "Zinc Ingot 99.99%", "Raw Material", "MT", "zinc_ingot"),
    ("RM-2001", "Corrugated Packing Box", "Packing", "MT", "packing"),
]


@dataclass
class Customer:
    code: str
    name: str
    credit_days: int


@dataclass
class Vendor:
    code: str
    name: str
    is_msme: bool


@dataclass
class Item:
    code: str
    name: str
    category: str
    uom: str
    family: str


def build_customers(rng: Rng) -> list[Customer]:
    terms = [30, 30, 45, 45, 45, 60, 60, 90]
    return [Customer(f"CUST{100 + i:04d}", name, rng.choice(terms))
            for i, name in enumerate(CUSTOMER_NAMES)]


def build_vendors(rng: Rng) -> list[Vendor]:
    return [Vendor(f"VEND{40 + i:04d}", name, rng.random() < 0.35)
            for i, name in enumerate(VENDOR_NAMES)]


def build_items() -> list[Item]:
    return [Item(*row) for row in ITEMS]


def build_rm_items() -> list[Item]:
    return [Item(*row) for row in RM_ITEMS]
