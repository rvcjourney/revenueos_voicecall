"""
app/core/invoicing.py — Generates QuickHowl's own branded GST tax invoice PDF
for a confirmed Razorpay payment.

Called from the subscription.charged webhook (app/api/webhooks.py) inside a
SAVEPOINT (db.begin_nested()) so a PDF-rendering or storage failure here can
never roll back the org-activation/credit-reset work that event also does --
an invoice that fails to generate is a support ticket, not a reason to leave
a paying customer's account suspended.

Tax split: Indian GST law splits the 18% into CGST 9% + SGST 9% when the
customer is in the same state QuickHowl is registered in (Maharashtra), or a
single IGST 18% when they're in any other state. amount_minor passed in is
already GST-inclusive (that's what Razorpay actually charged -- see
razorpay_client.py:sync_plan_to_razorpay), so subtotal is backed out of it
rather than recomputed from the plan's current price, which could have
changed since this specific historical charge.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import structlog
from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from xhtml2pdf import pisa

from app.config import settings
from app.core.invoice_constants import (
    GST_STATE_CODES,
    SAC_CODE,
    SELLER_ADDRESS_LINES,
    SELLER_COUNTRY,
    SELLER_GSTIN,
    SELLER_NAME,
    SELLER_STATE,
    SELLER_SUPPORT_EMAIL,
    state_with_code,
)
from app.core.razorpay_client import GST_RATE
from app.models.invoice import Invoice, InvoiceCounter
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization
from app.storage.backend import get_storage

log = structlog.get_logger(__name__)

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (" " + _ONES[ones] if ones else "")


def _three_digit_words(n: int) -> str:
    if n < 100:
        return _two_digit_words(n)
    hundreds, rest = divmod(n, 100)
    return _ONES[hundreds] + " Hundred" + (" " + _two_digit_words(rest) if rest else "")


def amount_in_words(rupees: int) -> str:
    """23600 -> 'Indian Rupees Twenty Three Thousand Six Hundred Only' (Indian
    numbering: crore/lakh/thousand, not the Western million/billion split)."""
    if rupees == 0:
        return "Indian Rupees Zero Only"
    crore, rem = divmod(rupees, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rem = divmod(rem, 1_000)
    parts = []
    if crore:
        parts.append(_two_digit_words(crore) + " Crore")
    if lakh:
        parts.append(_two_digit_words(lakh) + " Lakh")
    if thousand:
        parts.append(_two_digit_words(thousand) + " Thousand")
    if rem:
        parts.append(_three_digit_words(rem))
    return "Indian Rupees " + " ".join(parts) + " Only"


def _format_rupees(minor: int) -> str:
    return f"Rs.{minor / 100:,.2f}"


_INVOICE_HTML = Template("""
<html><head><style>
  @page { size: A4; margin: 2cm; }
  body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1a1a1a; }
  .header-table { width: 100%; margin-bottom: 16px; }
  .company-name { color: #2563eb; font-size: 22pt; font-weight: bold; }
  .doc-title { font-size: 16pt; font-weight: bold; text-align: right; }
  .doc-number { text-align: right; color: #555555; font-size: 9pt; }
  .meta-label { font-weight: bold; }
  .status-paid { color: #16a34a; font-weight: bold; }
  .addr-table { width: 100%; margin: 16px 0; }
  .addr-heading { color: #2563eb; font-weight: bold; margin-bottom: 4px; }
  .line-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  .line-table th { background-color: #eff6ff; color: #2563eb; text-align: left; padding: 8px; font-size: 9pt; }
  .line-table td { padding: 8px; border-bottom: 1px solid #e5e7eb; }
  .num { text-align: right; }
  .sac { color: #888888; font-size: 8pt; }
  .totals-table { width: 45%; margin-left: 55%; margin-top: 10px; }
  .totals-table td { padding: 4px 8px; }
  .total-row { font-weight: bold; background-color: #eff6ff; }
  .total-row .num { color: #2563eb; }
  .paid-line { text-align: right; font-weight: bold; color: #2563eb; margin-top: 12px; }
  .words-line { margin-top: 20px; font-size: 9pt; }
  .footer-note { margin-top: 4px; font-size: 8pt; color: #666666; }
</style></head>
<body>
  <table class="header-table"><tr>
    <td class="company-name">{{ seller_name }}</td>
    <td>
      <div class="doc-title">Tax Invoice</div>
      <div class="doc-number">{{ invoice_number }}</div>
    </td>
  </tr></table>

  <p><span class="meta-label">Date Paid</span> {{ date_paid }}</p>
  <p><span class="meta-label">Status</span> <span class="status-paid">PAID</span></p>
  <p><span class="meta-label">Receipt</span> {{ receipt_number }}</p>

  <table class="addr-table"><tr>
    <td width="50%" valign="top">
      <div class="addr-heading">From</div>
      <strong>{{ seller_name }}</strong><br/>
      {% for line in seller_address_lines %}{{ line }}<br/>{% endfor %}
      {{ seller_country }}<br/>
      GST: {{ seller_gstin }}<br/>
      {{ seller_support_email }}
    </td>
    <td width="50%" valign="top">
      <div class="addr-heading">Bill To</div>
      <strong>{{ customer_name }}</strong><br/>
      {% if customer_address_line %}{{ customer_address_line }}<br/>{% endif %}
      {% if customer_city %}{{ customer_city }}<br/>{% endif %}
      {{ customer_state }}{% if customer_pincode %}, {{ customer_pincode }}{% endif %}<br/>
      {{ seller_country }}<br/>
      {{ customer_email }}
      {% if customer_gstin %}<br/>GSTIN: {{ customer_gstin }}{% endif %}
    </td>
  </tr></table>

  <table class="line-table">
    <tr><th>Description</th><th class="num">Qty</th><th class="num">Unit Price</th><th class="num">Amount</th></tr>
    <tr>
      <td>{{ plan_description }}<br/><span class="sac">SAC {{ sac_code }}</span></td>
      <td class="num">1</td>
      <td class="num">{{ subtotal_formatted }}</td>
      <td class="num">{{ subtotal_formatted }}</td>
    </tr>
  </table>

  <table class="totals-table">
    <tr><td>Subtotal</td><td class="num">{{ subtotal_formatted }}</td></tr>
    {% if igst_minor %}
    <tr><td>IGST (18%)</td><td class="num">{{ igst_formatted }}</td></tr>
    {% else %}
    <tr><td>CGST (9%)</td><td class="num">{{ cgst_formatted }}</td></tr>
    <tr><td>SGST (9%)</td><td class="num">{{ sgst_formatted }}</td></tr>
    {% endif %}
    <tr class="total-row"><td>Total</td><td class="num">{{ total_formatted }}</td></tr>
  </table>

  <p class="paid-line">Amount Paid {{ total_formatted }}</p>

  <p class="words-line">Amount in words: {{ amount_in_words }}</p>
  <p class="footer-note">Place of supply: {{ place_of_supply }} &middot; Reverse charge: No</p>
  <p class="footer-note">This is a computer-generated invoice and does not require a signature.</p>
</body></html>
""")


def _render_invoice_pdf(**context) -> bytes:
    html = _INVOICE_HTML.render(**context)
    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf)
    if result.err:
        raise RuntimeError(f"invoice PDF rendering failed (err={result.err})")
    return buf.getvalue()


async def _next_invoice_number(db: AsyncSession, year: int) -> tuple[str, str]:
    """Returns (invoice_number, receipt_number), e.g. ("INV-2026-000021", "RCP-2026-000021").
    Race-safe under concurrent webhook deliveries: INSERT..ON CONFLICT DO NOTHING
    guarantees the year's counter row exists, then SELECT...FOR UPDATE locks it
    before incrementing, so two concurrent callers can never get the same number."""
    await db.execute(
        pg_insert(InvoiceCounter).values(year=year, last_seq=0).on_conflict_do_nothing(index_elements=["year"])
    )
    counter = await db.scalar(select(InvoiceCounter).where(InvoiceCounter.year == year).with_for_update())
    counter.last_seq += 1
    seq = f"{counter.last_seq:06d}"
    return f"INV-{year}-{seq}", f"RCP-{year}-{seq}"


async def generate_invoice_for_charge(
    db: AsyncSession,
    *,
    org: Organization,
    sub: Subscription,
    plan: Plan,
    amount_minor: int,
    razorpay_payment_id: str,
    customer_email: str | None = None,
) -> Invoice | None:
    """
    Idempotent on razorpay_payment_id -- Razorpay retries webhook delivery on
    any non-2xx/timeout, this must never double-invoice the same payment.
    Returns None (does not raise) if org.billing_state hasn't been collected
    yet -- the caller logs this; the org still gets activated/credited, just
    without an invoice until they fill in their billing address.
    """
    existing = await db.scalar(select(Invoice).where(Invoice.razorpay_payment_id == razorpay_payment_id))
    if existing:
        return existing

    customer_state = (org.billing_state or "").strip()
    if not customer_state:
        log.warning("invoice_skipped_no_billing_state", org_id=str(org.id), razorpay_payment_id=razorpay_payment_id)
        return None

    is_intra_state = customer_state.strip().lower() == SELLER_STATE.lower()

    # amount_minor is already GST-inclusive (baked into the Razorpay Plan
    # itself -- see razorpay_client.py:sync_plan_to_razorpay). Back the
    # subtotal out of it rather than recomputing from the plan's current
    # price, which may have changed since this specific charge happened.
    subtotal_minor = round(amount_minor / (1 + GST_RATE))
    tax_minor = amount_minor - subtotal_minor
    if is_intra_state:
        cgst_minor = tax_minor // 2
        sgst_minor = tax_minor - cgst_minor
        igst_minor = 0
    else:
        cgst_minor = 0
        sgst_minor = 0
        igst_minor = tax_minor

    now = datetime.now(timezone.utc)
    invoice_number, receipt_number = await _next_invoice_number(db, now.year)
    place_of_supply = state_with_code(customer_state) if customer_state in GST_STATE_CODES else customer_state

    pdf_bytes = _render_invoice_pdf(
        seller_name=SELLER_NAME,
        seller_address_lines=SELLER_ADDRESS_LINES,
        seller_country=SELLER_COUNTRY,
        seller_gstin=SELLER_GSTIN,
        seller_support_email=SELLER_SUPPORT_EMAIL,
        invoice_number=invoice_number,
        receipt_number=receipt_number,
        date_paid=now.strftime("%d %B %Y"),
        customer_name=org.name,
        customer_address_line=org.billing_address_line,
        customer_city=org.billing_city,
        customer_state=customer_state,
        customer_pincode=org.billing_pincode,
        customer_gstin=org.billing_gstin,
        customer_email=customer_email or "",
        plan_description=f"{plan.name} ({plan.credits_per_month:,} Credits)",
        sac_code=SAC_CODE,
        subtotal_formatted=_format_rupees(subtotal_minor),
        cgst_formatted=_format_rupees(cgst_minor),
        sgst_formatted=_format_rupees(sgst_minor),
        igst_formatted=_format_rupees(igst_minor),
        igst_minor=igst_minor,
        total_formatted=_format_rupees(amount_minor),
        # floor, not round -- "amount in words" should describe rupees actually
        # paid, never a figure rounded up past what was charged
        amount_in_words=amount_in_words(amount_minor // 100),
        place_of_supply=place_of_supply,
    )

    key = f"invoices/{org.id}/{invoice_number}.pdf"
    await get_storage().upload(settings.BUCKET_INVOICES, key, pdf_bytes, content_type="application/pdf")

    invoice = Invoice(
        org_id=org.id,
        subscription_id=sub.id,
        razorpay_payment_id=razorpay_payment_id,
        invoice_number=invoice_number,
        plan_name=plan.name,
        credits_per_month=plan.credits_per_month,
        subtotal_minor=subtotal_minor,
        cgst_minor=cgst_minor,
        sgst_minor=sgst_minor,
        igst_minor=igst_minor,
        total_minor=amount_minor,
        currency=plan.currency,
        customer_state=customer_state,
        place_of_supply=place_of_supply,
        storage_key=key,
        issued_at=now,
    )
    db.add(invoice)
    await db.flush()
    log.info("invoice_generated", org_id=str(org.id), invoice_number=invoice_number)
    return invoice
