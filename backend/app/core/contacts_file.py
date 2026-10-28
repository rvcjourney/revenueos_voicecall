"""
app/core/contacts_file.py — parse an uploaded contacts CSV/Excel into rows.

Shared by campaign contact upload (app/api/campaigns.py) and lead import
(app/api/leads.py) so both read files and normalise phones the same way.
"""
from __future__ import annotations

import io

import pandas as pd

from app.core.exceptions import ValidationError as AppValidationError

# Header names (after lowercase + spaces→"_") recognised as the contact's name
_NAME_COLUMNS = ("name", "full_name", "contact_name", "first_name", "customer_name", "client_name",
                 "person_name", "contact_person", "contact_person_name", "person", "owner_name",
                 "prospect_name", "lead_name")
# Otherwise any header containing "name" is the person's name — unless it names something else
_NOT_PERSON_NAME = ("company", "business", "firm", "organisation", "organization", "brand", "file",
                    "user", "product", "shop", "store", "city", "industry")


def find_name_column(columns) -> str | None:
    return next((c for c in columns if c in _NAME_COLUMNS), None) or next(
        (c for c in columns if "name" in c and not any(w in c for w in _NOT_PERSON_NAME)), None
    )
# Recognised as the phone column only when no header contains "phone"
_PHONE_FALLBACK_COLUMNS = (
    "contact", "contact_no", "contact_number", "mobile", "mobile_no", "mobile_number",
    "number", "cell", "whatsapp", "whatsapp_number",
)


def normalize_phone(raw: str) -> str:
    """E.164: strip spaces/dashes, add +91 if no country code."""
    phone = raw.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")
    return phone


def parse_contacts_file(contents: bytes, filename: str) -> list[dict]:
    """Rows of {name, phone, email, company, custom_fields}. name is None when
    the file has no name for that row. Every column but phone is kept in
    custom_fields (agent placeholders like {userName} are filled from them)."""
    fname = (filename or "").lower()
    try:
        if fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            df = pd.read_csv(io.BytesIO(contents))
    except Exception:
        raise AppValidationError(
            "Could not parse the uploaded file — ensure it is a valid CSV or Excel (.xlsx) file",
            errors=[],
        )

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    name_col = find_name_column(df.columns)
    phone_col = next((c for c in df.columns if "phone" in c), None) or next(
        (c for c in df.columns if c in _PHONE_FALLBACK_COLUMNS and c != name_col), None
    )
    if not phone_col:
        raise AppValidationError(
            "File must have a phone column (e.g. 'phone', 'mobile' or 'contact')", errors=[]
        )

    email_col = next((c for c in df.columns if "email" in c), None)
    company_col = next((c for c in df.columns if "company" in c), None)

    rows = []
    for _, row in df.iterrows():
        phone_val = row[phone_col]
        if pd.isna(phone_val) if isinstance(phone_val, float) else phone_val is None:
            continue
        # Pandas reads numeric columns as float — convert to int to strip ".0"
        if isinstance(phone_val, float):
            raw_phone = str(int(phone_val))
        else:
            raw_phone = str(phone_val).strip()
        if not raw_phone or raw_phone in ("nan", "None", ""):
            continue

        rows.append({
            "phone": normalize_phone(raw_phone),
            "name": str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else None,
            "email": str(row[email_col]).strip() if email_col and pd.notna(row.get(email_col)) else None,
            "company": str(row[company_col]).strip() if company_col and pd.notna(row.get(company_col)) else None,
            "custom_fields": {c: str(row[c]) for c in df.columns if c != phone_col and pd.notna(row.get(c))},
        })
    return rows
