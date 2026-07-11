from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceRequest(BaseModel):
    invoice_text: str


def clean_lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def parse_date(value):
    try:
        return parser.parse(value, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def extract_money(text):
    if not text:
        return None

    nums = re.findall(r"\d[\d,]*\.?\d*", text)

    if not nums:
        return None

    return float(nums[-1].replace(",", ""))


def parse_invoice(text):

    lines = clean_lines(text)

    invoice_no = None
    vendor = None
    date = None
    amount = None
    tax = None
    currency = None

    # -------------------------------------------------
    # Invoice Number
    # -------------------------------------------------

    patterns = [
        r"invoice\s*(?:no|number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"inv\s*(?:no|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"bill\s*(?:no|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)"
    ]

    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            invoice_no = m.group(1).strip()
            break

    if invoice_no is None:
        m = re.search(r"\b[A-Z]{1,6}-\d{2,10}\b", text)
        if m:
            invoice_no = m.group(0)

    # -------------------------------------------------
    # Vendor
    # -------------------------------------------------

    vendor_labels = [
        "vendor",
        "vendor name",
        "supplier",
        "supplier name",
        "seller",
        "sold by",
        "company",
        "company name",
        "business name",
        "from"
    ]

    for line in lines:

        lower = line.lower()

        for label in vendor_labels:

            if lower.startswith(label + ":"):
                vendor = line.split(":", 1)[1].strip()
                break

        if vendor:
            break

    if vendor is None:

        for i in range(len(lines) - 1):

            key = lines[i].lower().replace(":", "").strip()

            if key in vendor_labels:
                vendor = lines[i + 1]
                break

    # -------------------------------------------------
    # Date
    # -------------------------------------------------

    date_labels = [
        "invoice date",
        "bill date",
        "issue date",
        "issued on",
        "date"
    ]

    for line in lines:

        lower = line.lower()

        for label in date_labels:

            if lower.startswith(label + ":"):
                date = parse_date(line.split(":", 1)[1].strip())
                break

        if date:
            break

    if date is None:

        for i in range(len(lines) - 1):

            key = lines[i].lower().replace(":", "").strip()

            if key in date_labels:
                date = parse_date(lines[i + 1])
                break

    # -------------------------------------------------
    # Amount (Subtotal)
    # -------------------------------------------------

    amount_labels = [
        "subtotal",
        "sub total",
        "net amount",
        "amount before tax",
        "taxable amount"
    ]

    for line in lines:

        lower = line.lower()

        for label in amount_labels:

            if label in lower:
                amount = extract_money(line)
                break

        if amount is not None:
            break

    if amount is None:

        for i in range(len(lines) - 1):

            key = lines[i].lower().replace(":", "").strip()

            if key in amount_labels:
                amount = extract_money(lines[i + 1])
                break

    # -------------------------------------------------
    # Tax
    # -------------------------------------------------

    tax_total = 0.0
    found_tax = False

    for line in lines:

        lower = line.lower()

        if any(word in lower for word in [
            "cgst",
            "sgst",
            "igst",
            "gst",
            "vat",
            "sales tax",
            "tax amount",
            "tax"
        ]):

            # Skip total amount lines
            if "total" in lower and "tax" not in lower:
                continue

            value = extract_money(line)

            if value is not None:
                tax_total += value
                found_tax = True

    if found_tax:
        tax = tax_total

    # Fallback for tax label on one line and value on next
    if tax is None:

        for i in range(len(lines) - 1):

            key = lines[i].lower().replace(":", "").strip()

            if key in [
                "gst",
                "cgst",
                "sgst",
                "igst",
                "vat",
                "tax",
                "tax amount",
                "gst amount"
            ]:
                value = extract_money(lines[i + 1])

                if value is not None:
                    tax = value
                    break

    # -------------------------------------------------
    # Currency
    # -------------------------------------------------

    upper = text.upper()

    if "₹" in text or "INR" in upper or "RS." in upper or "RS " in upper:
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
