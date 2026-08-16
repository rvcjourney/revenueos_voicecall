"""
app/core/invoice_constants.py — Seller-side (QuickHowl) details printed on
every generated GST tax invoice (see app/core/invoicing.py). These are fixed
registration facts, not per-org data, hence plain constants rather than DB
config. Copied verbatim from the founder-supplied reference invoice, with the
company display name swapped from "QuickICP" to "QuickHowl" -- same legal
entity, GSTIN and registered address, per explicit founder confirmation.

GST state codes below are the standard, stable public GST jurisdiction codes
(the first two digits of every GSTIN) -- not something that changes.
"""
from __future__ import annotations

SELLER_NAME = "QuickHowl"
SELLER_ADDRESS_LINES = [
    "FIRST FLOOR, Reality Warehousing Pvt Ltd, GAT NO.-1337/1, Pune Nagar Road",
    "Above Reliance Smart, Wagholi, Pune",
]
SELLER_CITY = "Pune"
SELLER_STATE = "Maharashtra"
SELLER_COUNTRY = "India"
SELLER_GSTIN = "27AWYPK0264G1Z6"
SELLER_SUPPORT_EMAIL = "support@quickhowl.com"
SAC_CODE = "998313"

# State/UT name -> GST jurisdiction code (the "27" in "Maharashtra (27)" on the
# invoice's "Place of supply" line). Keys are matched case-insensitively.
GST_STATE_CODES: dict[str, str] = {
    "Jammu and Kashmir": "01",
    "Himachal Pradesh": "02",
    "Punjab": "03",
    "Chandigarh": "04",
    "Uttarakhand": "05",
    "Haryana": "06",
    "Delhi": "07",
    "Rajasthan": "08",
    "Uttar Pradesh": "09",
    "Bihar": "10",
    "Sikkim": "11",
    "Arunachal Pradesh": "12",
    "Nagaland": "13",
    "Manipur": "14",
    "Mizoram": "15",
    "Tripura": "16",
    "Meghalaya": "17",
    "Assam": "18",
    "West Bengal": "19",
    "Jharkhand": "20",
    "Odisha": "21",
    "Chhattisgarh": "22",
    "Madhya Pradesh": "23",
    "Gujarat": "24",
    "Dadra and Nagar Haveli and Daman and Diu": "26",
    "Maharashtra": "27",
    "Karnataka": "29",
    "Goa": "30",
    "Lakshadweep": "31",
    "Kerala": "32",
    "Tamil Nadu": "33",
    "Puducherry": "34",
    "Andaman and Nicobar Islands": "35",
    "Telangana": "36",
    "Andhra Pradesh": "37",
    "Ladakh": "38",
}


def state_with_code(state: str) -> str:
    """"Maharashtra" -> "Maharashtra (27)"; unknown/blank state -> returned as-is."""
    if not state:
        return state
    code = GST_STATE_CODES.get(state.strip())
    return f"{state} ({code})" if code else state
