from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
import re

app = FastAPI(title="Invoice Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceRequest(BaseModel):
    invoice_text: str


def extract_money(text):
    if not text:
        return None

    nums = re.findall(r"\d[\d,]*\.?\d*", text)

    if not nums:
        return None

    return float(nums[-1].replace(",", ""))


def extract_field(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def parse_invoice(text):

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    result = {
        "invoice_no": None,
        "date": None,
        "vendor": None,
        "amount": None,
        "tax": None,
        "currency": None,
    }

    # ---------------- Invoice Number ----------------

    invoice_patterns = [
        r"Invoice\s*(?:No|Number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Ref(?:erence)?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Inv\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Bill\s*(?:No|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
    ]

    result["invoice_no"] = extract_field(text, invoice_patterns)

    if result["invoice_no"] is None:
        m = re.search(r"\b[A-Z0-9]{1,8}[\/-][A-Z0-9\/-]+\b", text)
        if m:
            result["invoice_no"] = m.group(0)

    # ---------------- Vendor ----------------

    vendor_patterns = [
        r"Vendor\s*:\s*(.+)",
        r"Vendor\s*Name\s*:\s*(.+)",
        r"Seller\s*:\s*(.+)",
        r"Supplier\s*:\s*(.+)",
        r"Company\s*:\s*(.+)",
        r"Business\s*Name\s*:\s*(.+)",
        r"Client\s*:\s*(.+)",
        r"Sold\s*By\s*:\s*(.+)",
        r"From\s*:\s*(.+)",
    ]

    vendor = extract_field(text, vendor_patterns)

    if vendor:
        vendor = vendor.split("\n")[0].strip()

    if vendor is None:
        labels = {
            "vendor",
            "vendor name",
            "seller",
            "supplier",
            "company",
            "business name",
            "client",
            "sold by",
            "from",
        }

        for i in range(len(lines) - 1):
            key = lines[i].lower().replace(":", "").strip()
            if key in labels:
                vendor = lines[i + 1]
                break

    result["vendor"] = vendor

    # ---------------- Date ----------------

    date_patterns = [
        r"Invoice\s*Date\s*:\s*(.+)",
        r"Date\s*:\s*(.+)",
        r"Issued\s*:\s*(.+)",
        r"Issued\s*On\s*:\s*(.+)",
        r"Bill\s*Date\s*:\s*(.+)",
    ]

    raw_date = extract_field(text, date_patterns)

    if raw_date:
        try:
            result["date"] = parser.parse(
                raw_date,
                dayfirst=True
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    # ---------------- Amount ----------------

    amount_patterns = [
        r"Subtotal\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"Sub\s*Total\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"Amount\s*Before\s*Tax\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"Taxable\s*Amount\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"Net\s*Amount\s*[:\-]?\s*.*?([\d,]+\.\d+)",
    ]

    for p in amount_patterns:
        m = re.search(p, text, re.I)
        if m:
            result["amount"] = float(m.group(1).replace(",", ""))
            break

    # ---------------- Tax ----------------

    # Case 1: GST / VAT / IGST directly
    tax_patterns = [
        r"GST(?:\s*\([^)]*\))?\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"VAT(?:\s*\([^)]*\))?\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"IGST(?:\s*\([^)]*\))?\s*[:\-]?\s*.*?([\d,]+\.\d+)",
        r"Tax\s*Amount\s*[:\-]?\s*.*?([\d,]+\.\d+)",
    ]

    for p in tax_patterns:
        m = re.search(p, text, re.I)
        if m:
            result["tax"] = float(m.group(1).replace(",", ""))
            break

    # Case 2: CGST + SGST
    if result["tax"] is None:

        cgst = None
        sgst = None

        m = re.search(r"CGST.*?([\d,]+\.\d+)", text, re.I)
        if m:
            cgst = float(m.group(1).replace(",", ""))

        m = re.search(r"SGST.*?([\d,]+\.\d+)", text, re.I)
        if m:
            sgst = float(m.group(1).replace(",", ""))

        if cgst is not None and sgst is not None:
            result["tax"] = cgst + sgst
        elif cgst is not None:
            result["tax"] = cgst
        elif sgst is not None:
            result["tax"] = sgst

    # ---------------- Currency ----------------

    upper = text.upper()

    if "CURRENCY:" in upper:
        m = re.search(r"Currency\s*:\s*([A-Za-z]{3})", text, re.I)
        if m:
            result["currency"] = m.group(1).upper()

    if result["currency"] is None:

        if "₹" in text or "RS." in upper or "RS " in upper:
            result["currency"] = "INR"

        elif "USD" in upper or "$" in text:
            result["currency"] = "USD"

        elif "EUR" in upper or "€" in text:
            result["currency"] = "EUR"

        elif "GBP" in upper or "£" in text:
            result["currency"] = "GBP"

    return result


@app.post("/extract")
def extract(req: InvoiceRequest):
    return parse_invoice(req.invoice_text)
