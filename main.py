from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
import re

app = FastAPI()

# -------------------------
# Enable CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Request Model
# -------------------------
class InvoiceRequest(BaseModel):
    invoice_text: str


# -------------------------
# Helper Functions
# -------------------------
def extract_money(text):
    if not text:
        return None

    text = text.replace(",", "")

    m = re.search(r"(\d+(?:\.\d+)?)", text)

    if m:
        return float(m.group(1))

    return None


def extract_first(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


# -------------------------
# Invoice Parser
# -------------------------
def parse_invoice(text):

    # ---------------- Invoice Number ----------------

    invoice_patterns = [
        r"Invoice\s*(?:No|Number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Inv\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Bill\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
    ]

    invoice_no = extract_first(text, invoice_patterns)

    # Fallback for IDs like QX-2200
    if invoice_no is None:
        m = re.search(r"\b[A-Z]{1,6}-\d{2,10}\b", text)
        if m:
            invoice_no = m.group(0)

    # ---------------- Vendor ----------------

    vendor_patterns = [
        r"Vendor\s*:\s*(.+)",
        r"Supplier\s*:\s*(.+)",
        r"Sold\s*By\s*:\s*(.+)",
        r"Company\s*:\s*(.+)",
        r"From\s*:\s*(.+)",
    ]

    vendor = extract_first(text, vendor_patterns)

    if vendor:
        vendor = vendor.split("\n")[0].strip()

    # ---------------- Date ----------------

    date_patterns = [
        r"Invoice\s*Date\s*:\s*(.+)",
        r"Date\s*:\s*(.+)",
        r"Issued\s*On\s*:\s*(.+)",
    ]

    raw_date = extract_first(text, date_patterns)

    date = None

    if raw_date:
        try:
            date = parser.parse(raw_date, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            pass

    # ---------------- Amount (Subtotal) ----------------

    amount_patterns = [
        r"Subtotal\s*:\s*(.+)",
        r"Sub\s*Total\s*:\s*(.+)",
        r"Amount\s*Before\s*Tax\s*:\s*(.+)",
        r"Net\s*Amount\s*:\s*(.+)",
    ]

    raw_amount = extract_first(text, amount_patterns)
    amount = extract_money(raw_amount)

    # ---------------- Tax ----------------

    tax_patterns = [
        r"GST.*?:\s*(.+)",
        r"CGST.*?:\s*(.+)",
        r"SGST.*?:\s*(.+)",
        r"IGST.*?:\s*(.+)",
        r"VAT.*?:\s*(.+)",
        r"Sales\s*Tax.*?:\s*(.+)",
        r"Tax.*?:\s*(.+)",
    ]

    raw_tax = extract_first(text, tax_patterns)
    tax = extract_money(raw_tax)

    # ---------------- Currency ----------------

    currency = None

    upper = text.upper()

    if "₹" in text or "RS." in upper or "RS " in upper or "INR" in upper:
        currency = "INR"
    elif "$" in text or "USD" in upper:
        currency = "USD"
    elif "€" in text or "EUR" in upper:
        currency = "EUR"
    elif "£" in text or "GBP" in upper:
        currency = "GBP"

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }


# -------------------------
# API Endpoint
# -------------------------
@app.post("/extract")
def extract(req: InvoiceRequest):
    return parse_invoice(req.invoice_text)
