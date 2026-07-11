from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
import re

app = FastAPI()

# ------------------------
# Enable CORS
# ------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceRequest(BaseModel):
    invoice_text: str


# ------------------------
# Helpers
# ------------------------

def get_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_money(value):
    if value is None:
        return None

    value = value.replace(",", "")

    m = re.search(r"(\d+(?:\.\d+)?)", value)

    if m:
        return float(m.group(1))

    return None


def search_patterns(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def next_line_value(lines, labels):
    for i, line in enumerate(lines[:-1]):
        normalized = line.lower().replace(":", "").strip()

        if normalized in labels:
            return lines[i + 1].strip()

    return None


# ------------------------
# Main Parser
# ------------------------

def parse_invoice(text):

    lines = get_lines(text)

    # ---------------- Invoice Number ----------------

    invoice_no = search_patterns(text, [
        r"Invoice\s*(?:No|Number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Inv\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Bill\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)"
    ])

    if invoice_no is None:
        m = re.search(r"\b[A-Z]{1,6}-\d{2,10}\b", text)
        if m:
            invoice_no = m.group(0)

    # ---------------- Vendor ----------------

    vendor = search_patterns(text, [
        r"Vendor\s*Name\s*:\s*(.+)",
        r"Vendor\s*:\s*(.+)",
        r"Supplier\s*Name\s*:\s*(.+)",
        r"Supplier\s*:\s*(.+)",
        r"Seller\s*:\s*(.+)",
        r"Sold\s*By\s*:\s*(.+)",
        r"Company\s*:\s*(.+)",
        r"Company\s*Name\s*:\s*(.+)",
        r"Business\s*Name\s*:\s*(.+)",
        r"From\s*:\s*(.+)"
    ])

    if vendor is None:
        vendor = next_line_value(lines, [
            "vendor",
            "vendor name",
            "supplier",
            "supplier name",
            "seller",
            "company",
            "company name",
            "from"
        ])

    # ---------------- Date ----------------

    raw_date = search_patterns(text, [
        r"Invoice\s*Date\s*:\s*(.+)",
        r"Bill\s*Date\s*:\s*(.+)",
        r"Issue\s*Date\s*:\s*(.+)",
        r"Issued\s*On\s*:\s*(.+)",
        r"Date\s*:\s*(.+)"
    ])

    if raw_date is None:
        raw_date = next_line_value(lines, [
            "invoice date",
            "bill date",
            "issue date",
            "issued on",
            "date"
        ])

    date = None

    if raw_date:
        try:
            date = parser.parse(raw_date, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            pass

    # ---------------- Amount ----------------

    raw_amount = search_patterns(text, [
        r"Subtotal\s*:\s*(.+)",
        r"Sub\s*Total\s*:\s*(.+)",
        r"Net\s*Amount\s*:\s*(.+)",
        r"Amount\s*Before\s*Tax\s*:\s*(.+)",
        r"Taxable\s*Amount\s*:\s*(.+)"
    ])

    if raw_amount is None:
        raw_amount = next_line_value(lines, [
            "subtotal",
            "sub total",
            "net amount",
            "amount before tax",
            "taxable amount"
        ])

    amount = extract_money(raw_amount)

    # ---------------- Tax ----------------

    raw_tax = search_patterns(text, [
        r"GST.*?:\s*(.+)",
        r"CGST.*?:\s*(.+)",
        r"SGST.*?:\s*(.+)",
        r"IGST.*?:\s*(.+)",
        r"VAT.*?:\s*(.+)",
        r"Sales\s*Tax.*?:\s*(.+)",
        r"Tax\s*:\s*(.+)"
    ])

    if raw_tax is None:
        raw_tax = next_line_value(lines, [
            "gst",
            "cgst",
            "sgst",
            "igst",
            "vat",
            "sales tax",
            "tax"
        ])

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
        "currency": currency
    }


@app.post("/extract")
def extract(req: InvoiceRequest):
    return parse_invoice(req.invoice_text)
