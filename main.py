from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import re
from dateutil import parser

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

# ------------------------
# Input Model
# ------------------------

class InvoiceRequest(BaseModel):
    invoice_text: str


# ------------------------
# Helper Functions
# ------------------------

def parse_money(text):
    if not text:
        return None

    text = text.replace(",", "")

    m = re.search(r"(\d+(?:\.\d+)?)", text)

    if m:
        return float(m.group(1))

    return None


def parse_invoice(text):

    invoice_no = None
    vendor = None
    date = None
    amount = None
    tax = None
    currency = None

    m = re.search(r"Invoice\s*No[:\s]*([^\n]+)", text, re.IGNORECASE)
    if m:
        invoice_no = m.group(1).strip()

    m = re.search(r"Vendor[:\s]*(.+)", text, re.IGNORECASE)
    if m:
        vendor = m.group(1).strip()

    m = re.search(r"Date[:\s]*(.+)", text, re.IGNORECASE)
    if m:
        try:
            dt = parser.parse(m.group(1).strip(), dayfirst=True)
            date = dt.strftime("%Y-%m-%d")
        except:
            pass

    m = re.search(r"Subtotal[:\s]*(.+)", text, re.IGNORECASE)
    if m:
        amount = parse_money(m.group(1))

    m = re.search(r"(GST|Tax).*?:\s*(.+)", text, re.IGNORECASE)
    if m:
        tax = parse_money(m.group(2))

    if "₹" in text or "Rs" in text or "INR" in text:
        currency = "INR"

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }


# ------------------------
# Endpoint
# ------------------------

@app.post("/extract")
def extract(req: InvoiceRequest):
    return parse_invoice(req.invoice_text)
