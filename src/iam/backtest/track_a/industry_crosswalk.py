"""Crosswalk from Damodaran industry names used before 2015 to the current list.

Damodaran replaced his Value Line-based industry list with his own between the vintages
published in January 2014 and January 2015; 116 older names do not appear in the current list
of 94. Each old name maps to the single current industry its firms would most likely be in,
or to None when no single industry is safe (a wrong match applies the wrong beta, cost of
capital and multiples; a missing one is recorded as missing).

Built on 2026-10-25: GLM 5.3 Flash (OpenCode) and Gemini 4 Argon (AGY) each proposed a mapping
independently; they agreed on 100 names. A reviewer checked every entry against the current
list, overrode four agreed ones (the three electric-utility names belong in Power; Drugstore
has no single target) and decided the 16 disagreements. ``source`` records which applies.
"""

from __future__ import annotations

# old name -> (current name or None, source, note)
INDUSTRY_CROSSWALK: dict[str, tuple[str | None, str, str]] = {
    "Alternate Energy": (
        "Green & Renewable Energy",
        "GLM and AGY agree",
        "solar/fuel cell firms fit renewableenergy",
    ),
    "Aluminum": ("Metals & Mining", "GLM and AGY agree", "aluminum producers now in metals/mining"),
    "Auto Parts (OEM)": ("Auto Parts", "GLM and AGY agree", "direct rename"),
    "Auto Parts (Replacement)": (
        "Auto Parts",
        "GLM and AGY agree",
        "aftermarket parts folded into Auto Parts",
    ),
    "Automotive": ("Auto & Truck", "GLM and AGY agree", "likely OEM vehicle makers"),
    "Bank": (
        "Bank (Money Center)",
        "reviewer decision (GLM 'Banks (Regional)', AGY None)",
        "old list kept regional banks separately",
    ),
    "Bank (Canadian)": (None, "GLM and AGY agree", "geographic bucket, no single US match"),
    "Bank (Foreign)": (None, "GLM and AGY agree", "foreign banks, no sensible US match"),
    "Bank (Midwest)": (
        "Banks (Regional)",
        "GLM and AGY agree",
        "US Midwest banks are regional banks",
    ),
    "Beverage": (
        None,
        "reviewer decision (GLM 'Beverage (Soft)', AGY None)",
        "covered soft and alcoholic beverages",
    ),
    "Beverage (Soft Drink)": ("Beverage (Soft)", "GLM and AGY agree", "direct rename"),
    "Biotechnology": ("Drugs (Biotechnology)", "GLM and AGY agree", "direct match"),
    "Canadian Energy": (None, "GLM and AGY agree", "geographic bucket, mixed energy firms"),
    "Cement & Aggregates": (
        None,
        "reviewer decision (GLM 'Building Materials', AGY 'Construction Supplies')",
        "split between Building Materials and Construction Supplies",
    ),
    "Coal": ("Coal & Related Energy", "GLM and AGY agree", "direct match"),
    "Computer & Peripherals": ("Computers/Peripherals", "GLM and AGY agree", "direct rename"),
    "Computer Software": ("Software (System & Application)", "GLM and AGY agree", "direct match"),
    "Computer Software & Svcs": (
        "Software (System & Application)",
        "reviewer decision (GLM 'Software (System & Application)', AGY None)",
        "as GLM",
    ),
    "Computer Software/Svcs": (
        "Software (System & Application)",
        "reviewer decision (GLM 'Software (System & Application)', AGY None)",
        "as GLM",
    ),
    "Construction": (
        "Engineering/Construction",
        "GLM and AGY agree",
        "generic; homebuilders possible too",
    ),
    "Copper": ("Metals & Mining", "GLM and AGY agree", "copper miners now in metals/mining"),
    "Diversified Co.": ("Diversified", "GLM and AGY agree", "direct rename"),
    "Drug": ("Drugs (Pharmaceutical)", "GLM and AGY agree", "majority pharma firms"),
    "Drugstore": (
        None,
        "reviewer override (both helpers: 'Retail (Special Lines)')",
        "CVS and Walgreens sit in different current industries",
    ),
    "E-Commerce": (
        None,
        "reviewer decision (GLM 'Retail (General)', AGY None)",
        "online sellers of every kind",
    ),
    "Educational Services": ("Education", "GLM and AGY agree", "direct rename"),
    "Electric Util. (Central)": (
        "Power",
        "reviewer override (both helpers: 'Utility (General)')",
        "the current list has a separate Power industry",
    ),
    "Electric Utility (East)": (
        "Power",
        "reviewer override (both helpers: 'Utility (General)')",
        "the current list has a separate Power industry",
    ),
    "Electric Utility (West)": (
        "Power",
        "reviewer override (both helpers: 'Utility (General)')",
        "the current list has a separate Power industry",
    ),
    "Engineering": ("Engineering/Construction", "GLM and AGY agree", "engineering services bucket"),
    "Engineering & Const": ("Engineering/Construction", "GLM and AGY agree", "direct rename"),
    "Entertainment Tech": (
        "Entertainment",
        "GLM and AGY agree",
        "digital entertainment firms, uncertain mix",
    ),
    "Environmental": ("Environmental & Waste Services", "GLM and AGY agree", "direct rename"),
    "Financial Services": (
        "Financial Svcs. (Non-bank & Insurance)",
        "GLM and AGY agree",
        "non-bank financials",
    ),
    "Financial Svcs.": (
        "Financial Svcs. (Non-bank & Insurance)",
        "GLM and AGY agree",
        "abbreviated rename",
    ),
    "Financial Svcs. (Div.)": (
        "Financial Svcs. (Non-bank & Insurance)",
        "GLM and AGY agree",
        "diversified non-bank financials",
    ),
    "Foreign Electron/Entertn": (None, "GLM and AGY agree", "foreign electronics bucket, no match"),
    "Foreign Electronics": (None, "GLM and AGY agree", "geographic bucket, no match"),
    "Foreign Telecom.": (None, "GLM and AGY agree", "foreign telecom, no sensible match"),
    "Funeral Services": (
        "Business & Consumer Services",
        "GLM and AGY agree",
        "service firms in catch-all bucket",
    ),
    "Gold/Silver Mining": ("Precious Metals", "GLM and AGY agree", "direct match"),
    "Grand Total": (None, "GLM and AGY agree", "dataset total row, not an industry"),
    "Grocery": ("Retail (Grocery and Food)", "GLM and AGY agree", "direct match"),
    "Healthcare Equipment": ("Healthcare Products", "GLM and AGY agree", "direct match"),
    "Healthcare Facilities": (
        "Hospitals/Healthcare Facilities",
        "GLM and AGY agree",
        "direct match",
    ),
    "Healthcare Info Systems": (
        "Heathcare Information and Technology",
        "GLM and AGY agree",
        "same healthcare IT firms",
    ),
    "Healthcare Information": (
        "Heathcare Information and Technology",
        "GLM and AGY agree",
        "same healthcare IT firms",
    ),
    "Healthcare Services": (
        "Healthcare Support Services",
        "GLM and AGY agree",
        "generic services now support services",
    ),
    "Heavy Construction": ("Engineering/Construction", "GLM and AGY agree", "direct match"),
    "Heavy Truck & Equip": (
        "Machinery",
        "GLM and AGY agree",
        "trucks/equipment under machinery today",
    ),
    "Heavy Truck/Equip Makers": (
        "Machinery",
        "GLM and AGY agree",
        "trucks/equipment under machinery today",
    ),
    "Home Appliance": (
        None,
        "reviewer decision (GLM 'Electronics (Consumer & Office)', AGY 'Furn/Home Furnishings')",
        "no single current industry",
    ),
    "Human Resources": (
        "Business & Consumer Services",
        "GLM and AGY agree",
        "staffing/payroll now services bucket",
    ),
    "IT Services": (
        "Computer Services",
        "GLM and AGY agree",
        "IT services = computer services today",
    ),
    "Industrial Services": (
        "Business & Consumer Services",
        "reviewer decision (GLM 'Environmental & Waste Services', AGY 'Business & Consumer Services')",
        "as AGY",
    ),
    "Insurance (Diversified)": (
        "Insurance (General)",
        "GLM and AGY agree",
        "diversified insurers under general",
    ),
    "Insurance (Prop/Casualty)": ("Insurance (Prop/Cas.)", "GLM and AGY agree", "direct rename"),
    "Internet": ("Software (Internet)", "GLM and AGY agree", "internet firms; some retail today"),
    "Internet software and services": ("Software (Internet)", "GLM and AGY agree", "direct match"),
    "Investment (Domestic)": (
        "Investments & Asset Management",
        "GLM and AGY agree",
        "asset management closest today",
    ),
    "Investment Co.": (
        "Investments & Asset Management",
        "GLM and AGY agree",
        "fund/asset management bucket",
    ),
    "Investment Co. (Foreign)": (None, "GLM and AGY agree", "foreign funds, no match"),
    "Investment Co.(Foreign)": (None, "GLM and AGY agree", "foreign funds, no match"),
    "Investment Companies": (
        "Investments & Asset Management",
        "GLM and AGY agree",
        "fund/asset management bucket",
    ),
    "Manuf. Housing/RV": (
        None,
        "reviewer decision (GLM 'Recreation', AGY None)",
        "split between Homebuilding and Recreation",
    ),
    "Manuf. Housing/Rec Veh": (
        None,
        "reviewer decision (GLM 'Recreation', AGY None)",
        "split between Homebuilding and Recreation",
    ),
    "Maritime": ("Shipbuilding & Marine", "GLM and AGY agree", "direct match"),
    "Market": (None, "GLM and AGY agree", "placeholder bucket, no match"),
    "Med Supp Invasive": (
        "Healthcare Products",
        "GLM and AGY agree",
        "medical devices/supplies bucket",
    ),
    "Med Supp Non-Invasive": (
        "Healthcare Products",
        "GLM and AGY agree",
        "medical devices/supplies bucket",
    ),
    "Medical Services": (
        "Healthcare Support Services",
        "reviewer decision (GLM 'Healthcare Support Services', AGY None)",
        "as GLM",
    ),
    "Medical Supplies": ("Healthcare Products", "GLM and AGY agree", "direct match"),
    "Metal Fabricating": (
        "Machinery",
        "GLM and AGY agree",
        "fabricators are industrial manufacturers",
    ),
    "Metals & Mining (Div.)": ("Metals & Mining", "GLM and AGY agree", "direct rename"),
    "Natural Gas (Distrib.)": (
        "Utility (General)",
        "reviewer decision (GLM 'Oil/Gas Distribution', AGY 'Utility (General)')",
        "gas distribution utilities, as AGY",
    ),
    "Natural Gas (Div.)": (
        "Oil/Gas Distribution",
        "GLM and AGY agree",
        "producer/distribution mix, mostly midstream",
    ),
    "Natural Gas (Diversified)": (
        "Oil/Gas Distribution",
        "GLM and AGY agree",
        "producer/distribution mix, mostly midstream",
    ),
    "Natural Gas Utility": (
        "Utility (General)",
        "GLM and AGY agree",
        "regulated gas LDCs today under utilities",
    ),
    "Newspaper": ("Publishing & Newspapers", "GLM and AGY agree", "direct match"),
    "Office Equip & Supplies": (
        "Office Equipment & Services",
        "GLM and AGY agree",
        "direct rename",
    ),
    "Office Equip/Supplies": ("Office Equipment & Services", "GLM and AGY agree", "direct rename"),
    "Oilfield Services/Equip.": ("Oilfield Svcs/Equip.", "GLM and AGY agree", "direct rename"),
    "Other": (None, "GLM and AGY agree", "catch-all bucket, no match"),
    "Paper & Forest Products": ("Paper/Forest Products", "GLM and AGY agree", "direct rename"),
    "Petroleum (Integrated)": ("Oil/Gas (Integrated)", "GLM and AGY agree", "direct rename"),
    "Petroleum (Producing)": (
        "Oil/Gas (Production and Exploration)",
        "GLM and AGY agree",
        "direct rename",
    ),
    "Pharma & Drugs": ("Drugs (Pharmaceutical)", "GLM and AGY agree", "direct match"),
    "Pharmacy Services": (
        "Healthcare Support Services",
        "GLM and AGY agree",
        "PBM/pharmacy; mixed retail today",
    ),
    "Pipeline MLPs": (
        "Oil/Gas Distribution",
        "GLM and AGY agree",
        "pipelines now in distribution bucket",
    ),
    "Precision Instrument": (
        "Electronics (General)",
        "GLM and AGY agree",
        "instrument makers spread across several buckets",
    ),
    "Property Management": (
        "Real Estate (Operations & Services)",
        "GLM and AGY agree",
        "services/management current bucket",
    ),
    "Public/Private Equity": (
        "Investments & Asset Management",
        "GLM and AGY agree",
        "asset management bucket",
    ),
    "Publishing": ("Publishing & Newspapers", "GLM and AGY agree", "direct match"),
    "Publshing & Newspapers": ("Publishing & Newspapers", "GLM and AGY agree", "typo rename"),
    "Railroad": ("Transportation (Railroads)", "GLM and AGY agree", "direct match"),
    "Restaurant": ("Restaurant/Dining", "GLM and AGY agree", "direct match"),
    "Retail (Hardlines)": (
        "Retail (Special Lines)",
        "GLM and AGY agree",
        "mixed; building supply firms split off",
    ),
    "Retail (Internet)": (
        "Retail (General)",
        "reviewer decision (GLM 'Retail (General)', AGY None)",
        "as GLM",
    ),
    "Retail (Online)": (
        "Retail (General)",
        "reviewer decision (GLM 'Retail (General)', AGY None)",
        "as GLM; Damodaran dropped it in 2016",
    ),
    "Retail (Softlines)": (
        "Retail (Special Lines)",
        "GLM and AGY agree",
        "apparel retailers; no softlines bucket",
    ),
    "Retail Store": ("Retail (General)", "GLM and AGY agree", "general merchandise retailers"),
    "Retail/Wholesale Food": (
        "Food Wholesalers",
        "reviewer decision (GLM 'Food Wholesalers', AGY None)",
        "as GLM",
    ),
    "Securities Brokerage": ("Brokerage & Investment Banking", "GLM and AGY agree", "direct match"),
    "Semiconductor Cap Eq": ("Semiconductor Equip", "GLM and AGY agree", "direct rename"),
    "Semiconductor Cap Equip": ("Semiconductor Equip", "GLM and AGY agree", "direct rename"),
    "Steel (Integrated)": ("Steel", "GLM and AGY agree", "single current steel bucket"),
    "Telecom. Utility": ("Telecom. Services", "GLM and AGY agree", "telecom carriers/services"),
    "Textile": ("Apparel", "GLM and AGY agree", "fabrics/garments under apparel today"),
    "Thrift": ("Banks (Regional)", "GLM and AGY agree", "savings lenders closest to banks"),
    "Tire & Rubber": ("Rubber& Tires", "GLM and AGY agree", "direct rename"),
    "Toiletries/Cosmetics": (
        "Household Products",
        "GLM and AGY agree",
        "no personal products bucket today",
    ),
    "Trucking/Transp. Leasing": (
        "Trucking",
        "GLM and AGY agree",
        "dominant trucking; leasing split off",
    ),
    "Unclassified": (None, "GLM and AGY agree", "catch-all bucket, no match"),
    "Utility (Foreign)": (None, "GLM and AGY agree", "foreign utilities, no match"),
    "Water Utility": ("Utility (Water)", "GLM and AGY agree", "direct match"),
    "Wireless Networking": (
        "Telecom. Equipment",
        "reviewer decision (GLM 'Telecom (Wireless)', AGY 'Telecom. Equipment')",
        "equipment makers, as AGY",
    ),
}
