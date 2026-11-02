import math
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# ============================================================
# SRI KABILAN MOTORS - BILLING DASHBOARD
# Requires: streamlit >= 1.39  (pip install -U streamlit reportlab pandas)
# Run:      streamlit run app.py
#
# GST: prices entered are GST-INCLUSIVE (5% = CGST 2.5% + SGST 2.5%)
# ============================================================

# ---------------- SHOP DETAILS ----------------
SHOP_NAME = "SRI KABILAN MOTORS"
SHOP_TITLE = "Sri Kabilan Motors"
SHOP_ADDRESS = (
    "NO.205/1, CUDDALORE MAIN ROAD\n"
    "HOD.OFFICE VRIDDHACHALAM-606 001\n"
    "PROINCE : MUTHANDIKUPPAM-607805\n"
    "ARIYALUR-621704"
)
SHOP_ADDRESS_ONE_LINE = "No.205/1, Cuddalore Main Road, Vriddhachalam – 606 001, Ariyalur – 621704"
GSTIN = "33AWBPV4393E2ZE"
MOBILE_1 = "8903491764"
MOBILE_2 = "9865591764"
BANK_NAME = "INDIAN BANK"
ACCOUNT_NAME = "SRI KABILAN MOTORS"
ACCOUNT_NUMBER = "669035352"
IFSC = "IDIB000V031"
BRANCH = "VRIDDHACHALAM"
BILL_PREFIX = "SKM-"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BILL_FOLDER = os.path.join(BASE_DIR, "Bills")
os.makedirs(BILL_FOLDER, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "billing_history.db")

ROWS_PER_PAGE = 5

PAGE_DASH = "🏠  Dashboard"
PAGE_INVOICE = "🧾  New Bill (Tax Invoice)"
PAGE_QUOTE = "📋  Quotation"
PAGE_HISTORY = "🕘  Bill History"
PAGE_REPORTS = "📊  Reports"
PAGE_SETTINGS = "⚙️  Settings"
PAGES = [PAGE_DASH, PAGE_INVOICE, PAGE_QUOTE, PAGE_HISTORY, PAGE_REPORTS, PAGE_SETTINGS]


# ============================================================
# HELPERS
# ============================================================

def safe_filename(value):
    value = str(value).strip()
    value = re.sub(r'[\\/:*?"<>|]', "_", value)
    return value or "bill"


def inr(value):
    """Indian digit grouping: 307730 -> ₹ 3,07,730.00"""
    value = float(value or 0)
    whole, dec = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", whole[:-3])
        whole = head + "," + whole[-3:]
    return f"{'-' if value < 0 else ''}₹ {whole}.{dec}"


def nice_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d-%b-%Y")
    except ValueError:
        return str(value)


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_type TEXT NOT NULL,
                bill_number TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                mobile TEXT,
                bill_date TEXT NOT NULL,
                total_amount REAL NOT NULL,
                taxable_amount REAL NOT NULL,
                gst_amount REAL NOT NULL,
                pdf_blob BLOB NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(bill_type, bill_number)
            )
        """)
        connection.commit()


def save_bill_record(bill_type, bill_number, customer_name, mobile, bill_date,
                     total_amount, taxable_amount, gst_amount, pdf_bytes):
    with get_db_connection() as connection:
        connection.execute("""
            INSERT INTO bills (
                bill_type, bill_number, customer_name, mobile, bill_date,
                total_amount, taxable_amount, gst_amount, pdf_blob, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bill_type, bill_number) DO UPDATE SET
                customer_name=excluded.customer_name,
                mobile=excluded.mobile,
                bill_date=excluded.bill_date,
                total_amount=excluded.total_amount,
                taxable_amount=excluded.taxable_amount,
                gst_amount=excluded.gst_amount,
                pdf_blob=excluded.pdf_blob,
                created_at=excluded.created_at
        """, (
            bill_type, bill_number, customer_name, mobile, bill_date,
            total_amount, taxable_amount, gst_amount, sqlite3.Binary(pdf_bytes),
            datetime.now().isoformat(timespec="seconds")
        ))
        connection.commit()


BILL_COLUMNS = ("id, bill_type, bill_number, customer_name, mobile, bill_date, "
                "total_amount, taxable_amount, gst_amount")


def fetch_month_bills(month_value):
    month_key = month_value.strftime("%Y-%m")
    with get_db_connection() as connection:
        return connection.execute(
            f"SELECT {BILL_COLUMNS} FROM bills WHERE substr(bill_date,1,7)=? "
            "ORDER BY bill_date DESC, id DESC", (month_key,)).fetchall()


def fetch_all_bills():
    with get_db_connection() as connection:
        return connection.execute(
            f"SELECT {BILL_COLUMNS} FROM bills ORDER BY bill_date DESC, id DESC").fetchall()


def fetch_bill_pdf(record_id):
    with get_db_connection() as connection:
        return connection.execute(
            "SELECT bill_type, bill_number, pdf_blob FROM bills WHERE id = ?",
            (record_id,)).fetchone()


def fetch_monthly_summary():
    with get_db_connection() as connection:
        return connection.execute("""
            SELECT substr(bill_date,1,7) AS month, bill_type,
                   COUNT(*) AS cnt, SUM(total_amount) AS total,
                   SUM(taxable_amount) AS taxable, SUM(gst_amount) AS gst
            FROM bills GROUP BY month, bill_type ORDER BY month DESC
        """).fetchall()


def next_bill_number():
    with get_db_connection() as connection:
        rows = connection.execute("SELECT bill_number FROM bills").fetchall()
    nums = []
    for row in rows:
        match = re.match(rf"{re.escape(BILL_PREFIX)}(\d+)$", str(row["bill_number"]))
        if match:
            nums.append(int(match.group(1)))
    return f"{BILL_PREFIX}{max(nums, default=0) + 1:06d}"


initialize_database()


# ============================================================
# BILL CALCULATIONS
# ============================================================

def number_to_words(number):
    ones = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
            "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
            "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
    tens = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]

    def convert(n):
        n = int(n)
        if n < 20:
            return ones[n]
        if n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
        if n < 1000:
            return ones[n // 100] + " HUNDRED" + (" " + convert(n % 100) if n % 100 else "")
        if n < 100000:
            return convert(n // 1000) + " THOUSAND" + (" " + convert(n % 1000) if n % 1000 else "")
        if n < 10000000:
            return convert(n // 100000) + " LAKH" + (" " + convert(n % 100000) if n % 100000 else "")
        return convert(n // 10000000) + " CRORE" + (" " + convert(n % 10000000) if n % 10000000 else "")

    number = round(float(number), 2)
    rupees = int(number)
    paise = int(round((number - rupees) * 100))
    result = convert(rupees) if rupees else "ZERO"
    result += " RUPEES"
    if paise:
        result += " AND " + convert(paise) + " PAISE"
    return result + " ONLY"


def calculate_gst_inclusive(total_inclusive, gst_rate):
    total_inclusive = round(float(total_inclusive), 2)
    gst_rate = max(float(gst_rate), 0.0)
    if gst_rate == 0:
        return total_inclusive, 0.0, 0.0, 0.0
    taxable_value = total_inclusive / (1 + gst_rate / 100)
    total_gst = total_inclusive - taxable_value
    cgst = round(total_gst / 2, 2)
    sgst = round(total_gst / 2, 2)
    taxable_value = round(taxable_value, 2)
    rounding = round(total_inclusive - (taxable_value + cgst + sgst), 2)
    return taxable_value, cgst, sgst, rounding


def calculate_item(description, company_name, model_no, warranty_type_1,
                   warranty_months_1, warranty_type_2, warranty_months_2,
                   quantity, hsn, unit_price, bill_format="Spare Bill", bike_details=None):
    return {
        "description": description, "company_name": company_name, "model_no": model_no,
        "warranty_type_1": warranty_type_1, "warranty_months_1": warranty_months_1,
        "warranty_type_2": warranty_type_2, "warranty_months_2": warranty_months_2,
        "quantity": quantity, "hsn": hsn, "unit_price": unit_price,
        "gross_amount": round(quantity * unit_price, 2),
        "bill_format": bill_format, "bike_details": bike_details or {},
    }


def calculate_bill(items, bill_type, gst_rate):
    gross_total = round(sum(item["gross_amount"] for item in items), 2)
    if bill_type == "QUOTATION":
        return gross_total, gross_total, 0.0, 0.0, 0.0, gross_total
    subtotal = cgst = sgst = 0.0
    for item in items:
        taxable, item_cgst, item_sgst, _ = calculate_gst_inclusive(item["gross_amount"], gst_rate)
        subtotal += taxable
        cgst += item_cgst
        sgst += item_sgst
    subtotal, cgst, sgst = round(subtotal, 2), round(cgst, 2), round(sgst, 2)
    rounding = round(gross_total - subtotal - cgst - sgst, 2)
    grand_total = round(subtotal + cgst + sgst + rounding, 2)
    return gross_total, subtotal, cgst, sgst, rounding, grand_total


def warranty_text(item):
    parts = []
    if item["warranty_type_1"].strip() and item["warranty_months_1"] > 0:
        parts.append(f"{item['warranty_type_1'].strip()} warranty - {item['warranty_months_1']} months")
    if item["warranty_type_2"].strip() and item["warranty_months_2"] > 0:
        parts.append(f"{item['warranty_type_2'].strip()} warranty - {item['warranty_months_2']} months")
    if parts:
        parts.append(f"Total Warranty - {item['warranty_months_1'] + item['warranty_months_2']} months")
    return "<br/>".join(parts)


# ============================================================
# PDF
# ============================================================

def create_bill_pdf(bill_type, bill_number, bill_date, customer_name, customer_address,
                    mobile, items, payment_mode, paid_amount, notes, gst_rate):
    filename = os.path.join(BILL_FOLDER, f"{bill_type.lower()}_{safe_filename(bill_number)}.pdf")
    gross_total, subtotal, cgst, sgst, rounding, grand_total = calculate_bill(items, bill_type, gst_rate)
    balance = round(grand_total - paid_amount, 2)

    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=10 * mm, leftMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=9 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("BillTitle", parent=styles["Normal"], fontSize=12, leading=14,
                                 alignment=TA_CENTER, fontName="Helvetica-Bold")
    normal_style = ParagraphStyle("BillNormal", parent=styles["Normal"], fontSize=8.2, leading=10)
    small_style = ParagraphStyle("BillSmall", parent=normal_style, fontSize=7.5, leading=9)
    center_style = ParagraphStyle("BillCenter", parent=normal_style, alignment=TA_CENTER)
    right_style = ParagraphStyle("BillRight", parent=normal_style, alignment=TA_RIGHT)

    box_style = [
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    single_box = [
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    elements = [Paragraph(bill_type.upper(), title_style), Spacer(1, 2 * mm)]

    shop_text = f"<b>{SHOP_NAME}</b><br/>" + SHOP_ADDRESS.replace("\n", "<br/>")
    contact_text = f"<b>GSTIN/UIN : {GSTIN}</b><br/><b>MOB NO : {MOBILE_1}</b><br/>{MOBILE_2}"
    header = Table([[Paragraph(shop_text, normal_style), Paragraph(contact_text, right_style)]],
                   colWidths=[108 * mm, 67 * mm])
    header.setStyle(TableStyle(box_style))
    elements.append(header)

    customer_text = (f"<b>Customer: {customer_name}</b><br/>Mobile: {mobile}<br/>"
                     + customer_address.replace("\n", "<br/>"))
    document_text = f"<b>{bill_type} NO : {bill_number}</b><br/><b>DATE : {bill_date}</b>"
    customer_table = Table([[Paragraph(customer_text, normal_style), Paragraph(document_text, right_style)]],
                           colWidths=[108 * mm, 67 * mm])
    customer_table.setStyle(TableStyle(box_style))
    elements.append(customer_table)
    elements.append(Spacer(1, 2 * mm))

    table_data = [[
        Paragraph("<b>SL<br/>NO</b>", center_style),
        Paragraph("<b>DESCRIPTION / PRODUCT DETAILS</b>", center_style),
        Paragraph("<b>HSN/<br/>SAC</b>", center_style),
        Paragraph("<b>QTY</b>", center_style),
        Paragraph("<b>RATE<br/>(GST INCL.)</b>", center_style),
        Paragraph("<b>AMOUNT<br/>(GST INCL.)</b>", center_style),
    ]]
    for index, item in enumerate(items, start=1):
        details = f"<b>{item['description']}</b>"
        bike = item.get("bike_details", {})
        if item.get("bill_format") == "Bike Bill":
            details += f"<br/><b>Company:</b> {item['company_name']}"
            details += f"<br/><b>Model:</b> {item['model_no']}"
            details += "<br/><b>Motor / Controller Warranty:</b> 12 months"
            battery_warranty = "; ".join(
                f"{label}: {bike.get(key, 0)} months" for label, key in
                [("Replacement", "battery_replacement_months"), ("Pro-rata service", "battery_prorata_months")]
                if bike.get(key, 0))
            charger_warranty = "; ".join(
                f"{label}: {bike.get(key, 0)} months" for label, key in
                [("Replacement", "charger_replacement_months"), ("Pro-rata service", "charger_prorata_months")]
                if bike.get(key, 0))
            for label, value in [("Colour", bike.get("colour", "")), ("Chassis Number", bike.get("chassis_no", "")),
                                 ("Motor Number", bike.get("motor_no", "")), ("Battery Type", bike.get("battery_type", "")),
                                 ("Battery Number", bike.get("battery_no", "")), ("Battery Warranty", battery_warranty),
                                 ("Charger Name", bike.get("charger_name", "")), ("Charger Number", bike.get("charger_no", "")),
                                 ("Charger Warranty", charger_warranty)]:
                if value:
                    details += f"<br/><b>{label}:</b> {value}"
        if item["company_name"].strip():
            if item.get("bill_format") != "Bike Bill":
                details += f"<br/><b>Company:</b> {item['company_name']}"
        if item["model_no"].strip() and item.get("bill_format") != "Bike Bill":
            details += f"<br/><b>Model No:</b> {item['model_no']}"
        warranty = warranty_text(item)
        if warranty:
            details += f"<br/><b>Warranty:</b><br/>{warranty}"
        table_data.append([
            str(index), Paragraph(details, small_style), item["hsn"],
            "" if item.get("no_quantity") else str(item["quantity"]),
            "" if item.get("no_quantity") else f"{item['unit_price']:,.2f}",
            f"{item['gross_amount']:,.2f}",
        ])
    while len(table_data) < 8:
        table_data.append(["", Spacer(1, 7 * mm), "", "", "", ""])

    item_table = Table(table_data,
                       colWidths=[9 * mm, 78 * mm, 19 * mm, 15 * mm, 27 * mm, 27 * mm],
                       repeatRows=1, splitByRow=1)
    item_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(item_table)

    if bill_type == "QUOTATION":
        totals_data = [["", "", "", "TOTAL", f"{grand_total:,.2f}"]]
    else:
        totals_data = [
            ["", "", "", "TAXABLE SUBTOTAL", f"{subtotal:,.2f}"],
            ["", "", "", f"CGST @ {gst_rate / 2:g}%", f"{cgst:,.2f}"],
            ["", "", "", f"SGST @ {gst_rate / 2:g}%", f"{sgst:,.2f}"],
        ]
        if rounding != 0:
            totals_data.append(["", "", "", "ROUNDING", f"{rounding:,.2f}"])
        totals_data.append(["", "", "", "GRAND TOTAL", f"{grand_total:,.2f}"])
    totals_table = Table(totals_data, colWidths=[9 * mm, 78 * mm, 19 * mm, 49 * mm, 20 * mm])
    totals_table.setStyle(TableStyle([
        ("GRID", (3, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (3, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (3, 0), (-1, -1), 8.0),
        ("TOPPADDING", (3, 0), (-1, -1), 4), ("BOTTOMPADDING", (3, 0), (-1, -1), 4),
    ]))
    elements.append(totals_table)

    words_table = Table([[Paragraph(f"<b>Amount in Words : {number_to_words(grand_total)}</b>", normal_style)]],
                        colWidths=[175 * mm])
    words_table.setStyle(TableStyle(single_box))
    elements.append(words_table)

    payment_text = (f"<b>Payment Mode : {payment_mode}</b><br/>"
                    f"Paid Amount : ₹{paid_amount:,.2f}<br/>Balance Amount : ₹{balance:,.2f}")
    payment_table = Table([[Paragraph(payment_text, normal_style)]], colWidths=[175 * mm])
    payment_table.setStyle(TableStyle(single_box))
    elements.append(payment_table)

    bank_text = (f"<b>Bank Details:</b><br/>A/C Holder Name : {ACCOUNT_NAME}<br/>"
                 f"Company Bank Name : {BANK_NAME}<br/>Account No : {ACCOUNT_NUMBER}<br/>"
                 f"IFSC CODE : {IFSC}<br/>BRANCH : {BRANCH}")
    bank_table = Table([[Paragraph(bank_text, normal_style)]], colWidths=[175 * mm])
    bank_table.setStyle(TableStyle(single_box))
    elements.append(bank_table)

    notes_text = ("<b>TERMS & CONDITIONS E. & O.E.</b><br/>1. Goods once cannot be taken back.<br/>"
                  "2. Payment as agreed.<br/>3. E. & O.E.")
    if notes.strip():
        notes_text += "<br/><b>Notes:</b> " + notes.replace("\n", "<br/>")

    terms_and_signatures = Table(
        [
            [Paragraph(notes_text, normal_style), Paragraph(f"<b>For {SHOP_NAME}</b>", right_style)],
            ["", ""],
            [Paragraph("<b>Customer Signature</b>", normal_style),
             Paragraph("<b>Authorised Signatory</b>", right_style)],
        ],
        colWidths=[87.5 * mm, 87.5 * mm], rowHeights=[18 * mm, 10 * mm, 10 * mm],
    )
    terms_and_signatures.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 2), (-1, 2), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 2), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(terms_and_signatures)
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph("<b>This is a Computer Generated Bill</b>", center_style))

    doc.build(elements)
    return filename


# ============================================================
# STREAMLIT SETUP + CSS (matches the dashboard design)
# ============================================================

st.set_page_config(page_title="Sri Kabilan Motors | Billing", page_icon="🛵",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea { font-family: 'Inter', sans-serif !important; }
.stApp { background: #f3f6fc; color: #12214a; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { max-width: 1500px; padding: 1.2rem 2rem 3rem; }

/* ---------- SIDEBAR ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0b2d73 0%,#0a2159 55%,#071a47 100%); min-width: 300px !important; }
[data-testid="stSidebar"] > div:first-child { padding-top: .5rem; }
.side-brand { display:flex; align-items:center; gap:14px; padding: 10px 6px 18px; }
.side-logo { width:54px; height:54px; border-radius:14px; background:rgba(255,255,255,.12); display:flex; align-items:center; justify-content:center; font-size:30px; }
.side-name { color:#fff; font-weight:800; font-size:21px; line-height:1.15; letter-spacing:.3px; }
.side-line { height:1px; background:rgba(255,255,255,.18); margin: 0 0 18px; }
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 6px; }
[data-testid="stSidebar"] div[role="radiogroup"] label { width:100%; padding: 14px 16px; border-radius: 13px; cursor:pointer; transition: background .15s; }
[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display:none; }
[data-testid="stSidebar"] div[role="radiogroup"] label p { color:#fff !important; font-weight:600; font-size:16px; }
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) { background:#1f63d9; box-shadow:0 6px 18px rgba(31,99,217,.45); }
.side-bike { margin-top: 40px; opacity:.9; }

/* ---------- TOP HEADER ---------- */
.shop-head h1 { margin:0 0 6px; font-size:38px; font-weight:800; color:#0b1b4a; letter-spacing:-.5px; }
.shop-head .line { color:#2a3a63; font-size:15.5px; margin-top:5px; }
.shop-head .sep { color:#9aa6c4; margin:0 12px; }
.st-key-btn_quote button { height:66px; border-radius:16px; background:#f6efff; border:2px solid #c3a4f5; }
.st-key-btn_quote button p { color:#6d28d9 !important; font-weight:700; font-size:18px; }
.st-key-btn_newbill button { height:66px; border-radius:16px; border:0; background:linear-gradient(135deg,#0c58d0,#0a2f86); box-shadow:0 8px 20px rgba(12,70,170,.35); }
.st-key-btn_newbill button p { color:#fff !important; font-weight:700; font-size:18px; }

/* ---------- WHITE CARDS ---------- */
[class*="st-key-card_"] { background:#fff; border-radius:24px; padding:22px 26px 26px; box-shadow:0 6px 26px rgba(30,60,130,.08); margin-bottom:18px; }
.card-title { font-size:23px; font-weight:800; color:#0b1b4a; display:flex; align-items:center; gap:12px; padding-top:6px; }
.month-pill { background:#dbe9fd; color:#1a4fb0; font-size:15px; font-weight:600; padding:6px 16px; border-radius:20px; }

/* ---------- KPI CARDS ---------- */
.kpi { border-radius:18px; padding:20px 22px; min-height:158px; border:1px solid rgba(255,255,255,.8); box-shadow:0 4px 14px rgba(40,70,140,.10); }
.kpi-blue   { background:linear-gradient(135deg,#e4f0ff,#c6dcfa); }
.kpi-green  { background:linear-gradient(135deg,#e7f9ee,#c5eed5); }
.kpi-orange { background:linear-gradient(135deg,#fff1e1,#fbd9b4); }
.kpi-purple { background:linear-gradient(135deg,#f5ecff,#e1d1fb); }
.kpi-top { display:flex; gap:14px; align-items:center; }
.kpi-icon { width:50px; height:50px; border-radius:50%; background:rgba(255,255,255,.7); display:flex; align-items:center; justify-content:center; font-size:24px; flex-shrink:0; }
.kpi-title { font-weight:700; color:#12214a; font-size:16px; line-height:1.2; }
.kpi-sub { font-size:13px; color:#44537c; }
.kpi-value { font-size:34px; font-weight:800; color:#0b1b4a; margin:14px 0 6px; letter-spacing:-.5px; }
.kpi-delta { font-size:14px; color:#44537c; }
.delta { font-weight:700; }
.delta.up { color:#16a34a; } .delta.down { color:#dc2626; } .delta.flat { color:#7b88a8; }

/* ---------- INPUTS ---------- */
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div, div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stDateInput"] input {
    border-radius: 12px; border-color:#dfe5f1; background:#fff; }
div[data-testid="stTextInput"] input { padding: 11px 14px; }

/* ---------- BILL TABLE ---------- */
.st-key-tbl_head { background:#dfeafb; border-radius:12px; padding:12px 14px; margin-top:8px; }
.th { font-weight:700; color:#12214a; font-size:15.5px; }
[class*="st-key-row_"] { border-bottom:1px solid #edf0f7; padding:6px 14px; }
[class*="st-key-row_"] [data-testid="stHorizontalBlock"], .st-key-tbl_head [data-testid="stHorizontalBlock"] { align-items:center; }
.td { font-size:15.5px; color:#1a2a55; }
.td-b { font-size:15.5px; color:#0b1b4a; font-weight:700; }
.td-amt { font-size:15.5px; color:#0b1b4a; font-weight:700; text-align:right; padding-right:12px; }
.pill { display:inline-block; padding:5px 16px; border-radius:18px; font-size:14.5px; font-weight:500; }
.pill-t { background:#d6e8fc; color:#1a5bb8; } .pill-q { background:#ecddfc; color:#7a2fd0; }
[class*="st-key-view_"] button { border:1.5px solid #2f6fe0; background:#f2f7ff; border-radius:10px; min-height:40px; }
[class*="st-key-view_"] button p { color:#1550c0 !important; font-weight:600; }
.st-key-pager button { min-height:42px; border-radius:12px; padding:0; border:1px solid #e1e6f1; background:#fff; }
.st-key-pager button p { font-weight:600; color:#12214a; font-size:15px; }
.st-key-pager button[kind="primary"] { background:#0f4fc2; border-color:#0f4fc2; }
.st-key-pager button[kind="primary"] p { color:#fff !important; }
.showing { color:#2a3a63; font-size:16px; padding-top:10px; }

/* ---------- GENERIC ---------- */
div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button { border-radius:12px; min-height:44px; font-weight:600; }
div[data-testid="stButton"] > button[kind="primary"] { background:#0f4fc2; border-color:#0f4fc2; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #e3eaf6; padding:14px 18px; border-radius:14px; box-shadow:0 3px 12px rgba(30,60,130,.05); }
[data-testid="stExpander"] { background:#fff; border:1px solid #e3eaf6; border-radius:14px; }
h3 { color:#0b1b4a; font-weight:800 !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# STATE / CALLBACKS
# ============================================================

def month_options(count=24):
    year, month = date.today().year, date.today().month
    out = []
    for _ in range(count):
        out.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return out


MONTHS = {d.strftime("%B %Y"): d for d in month_options()}
MONTH_LABELS = list(MONTHS)

st.session_state.setdefault("nav_page", PAGE_DASH)
st.session_state.setdefault("dash_month", MONTH_LABELS[0])
st.session_state.setdefault("tbl_month", st.session_state.dash_month)
st.session_state.setdefault("manual_items", [])


def goto(page):
    st.session_state.nav_page = page


def sync_from_dash():
    st.session_state.tbl_month = st.session_state.dash_month


def sync_from_tbl():
    st.session_state.dash_month = st.session_state.tbl_month


def set_pager(key, value):
    st.session_state[key] = value


def open_bill(record_id):
    st.session_state.view_bill_record_id = record_id


def close_bill():
    st.session_state.pop("view_bill_record_id", None)


def clear_items():
    st.session_state.manual_items = []
    st.session_state.pop("generated_pdf_bytes", None)
    st.session_state.bill_number_input = next_bill_number()


# ============================================================
# SIDEBAR
# ============================================================

BIKE_SVG = """
<svg class="side-bike" viewBox="0 0 300 160" width="100%" xmlns="http://www.w3.org/2000/svg">
 <g fill="none" stroke="#8fb2ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity=".28">
  <circle cx="70" cy="115" r="30"/><circle cx="235" cy="115" r="30"/>
  <path d="M70 115 L112 62 L172 62 L204 115 M112 62 L100 40 L132 40 M172 62 L196 38 L228 38 M204 115 L235 115 M112 115 L150 115 M112 62 L150 115"/>
 </g>
</svg>
"""

with st.sidebar:
    st.markdown(
        '<div class="side-brand"><div class="side-logo">🛵</div>'
        '<div class="side-name">SRI KABILAN<br>MOTORS</div></div><div class="side-line"></div>',
        unsafe_allow_html=True)
    st.radio("Navigation", PAGES, key="nav_page", label_visibility="collapsed")
    st.markdown(BIKE_SVG, unsafe_allow_html=True)


# ============================================================
# SHARED UI PIECES
# ============================================================

def render_top_header():
    left, quote_col, bill_col = st.columns([7, 1.9, 2.6], vertical_alignment="center")
    left.markdown(
        f'<div class="shop-head"><h1>{SHOP_TITLE}</h1>'
        f'<div class="line">📍 {SHOP_ADDRESS_ONE_LINE}</div>'
        f'<div class="line">🪪 GSTIN : {GSTIN}<span class="sep">|</span>📞 {MOBILE_1} / {MOBILE_2}</div></div>',
        unsafe_allow_html=True)
    quote_col.button("📝 Quotation", key="btn_quote", use_container_width=True,
                     on_click=goto, args=(PAGE_QUOTE,))
    bill_col.button("＋ New Bill (Tax Invoice)", key="btn_newbill", type="primary",
                    use_container_width=True, on_click=goto, args=(PAGE_INVOICE,))
    st.write("")


def pct_delta(current, previous):
    if not previous:
        return '<span class="delta flat">— no data last month</span>'
    pct = (current - previous) / previous * 100
    up = pct >= 0
    return (f'<span class="delta {"up" if up else "down"}">{"↑" if up else "↓"} '
            f'{"+" if up else "-"}{abs(pct):.0f}%</span> from last month')


def kpi_card(tone, icon, title, sub, value, delta=""):
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi kpi-{tone}"><div class="kpi-top"><div class="kpi-icon">{icon}</div>'
            f'<div><div class="kpi-title">{title}</div>{sub_html}</div></div>'
            f'<div class="kpi-value">{value}</div><div class="kpi-delta">{delta}</div></div>')


def month_stats(bills):
    invoices = [r for r in bills if r["bill_type"] == "INVOICE"]
    return {
        "count": len(bills),
        "total": sum(float(r["total_amount"] or 0) for r in invoices),
        "taxable": sum(float(r["taxable_amount"] or 0) for r in invoices),
        "gst": sum(float(r["gst_amount"] or 0) for r in invoices),
    }


COLS = [0.5, 1.5, 2.0, 1.8, 1.5, 1.5, 1.5, 1.3]


def render_bill_table(title, bills, prefix, show_month=False):
    """White card with search, table rows, pagination and bill viewer."""
    page_key = f"page_{prefix}"
    st.session_state.setdefault(page_key, 1)

    with st.container(key=f"card_table_{prefix}"):
        if show_month:
            h1, h2, h3 = st.columns([4.3, 3.3, 2.2], vertical_alignment="center")
        else:
            h1, h2 = st.columns([6, 4], vertical_alignment="center")
            h3 = None
        h1.markdown(f'<div class="card-title">🧾 {title}</div>', unsafe_allow_html=True)
        search = h2.text_input("Search", placeholder="🔍  Search by Bill No, Name or Phone...",
                               key=f"search_{prefix}", label_visibility="collapsed")
        if h3 is not None:
            h3.selectbox("Month", MONTH_LABELS, key="tbl_month", on_change=sync_from_tbl,
                         label_visibility="collapsed")

        query = search.strip().lower()
        if query:
            bills = [r for r in bills if query in " ".join(
                [str(r["bill_number"] or ""), str(r["customer_name"] or ""), str(r["mobile"] or "")]).lower()]

        signature = (query, st.session_state.dash_month)
        if st.session_state.get(f"sig_{prefix}") != signature:
            st.session_state[f"sig_{prefix}"] = signature
            st.session_state[page_key] = 1

        total = len(bills)
        total_pages = max(1, math.ceil(total / ROWS_PER_PAGE))
        current = min(max(1, st.session_state[page_key]), total_pages)
        start = (current - 1) * ROWS_PER_PAGE
        page_rows = bills[start:start + ROWS_PER_PAGE]

        if not page_rows:
            st.info("No bills found for this selection yet. Generated documents will appear here.")
            return

        with st.container(key="tbl_head"):
            for col, text in zip(st.columns(COLS),
                                 ["#", "Bill No", "Customer Name", "Phone No", "Bill Type", "Amount (₹)", "Date", "Action"]):
                col.markdown(f'<span class="th">{text}</span>', unsafe_allow_html=True)

        for offset, row in enumerate(page_rows):
            is_quote = row["bill_type"] == "QUOTATION"
            with st.container(key=f"row_{prefix}_{row['id']}"):
                c = st.columns(COLS)
                c[0].markdown(f'<span class="td">{start + offset + 1}</span>', unsafe_allow_html=True)
                c[1].markdown(f'<span class="td">{row["bill_number"]}</span>', unsafe_allow_html=True)
                c[2].markdown(f'<span class="td-b">{row["customer_name"]}</span>', unsafe_allow_html=True)
                c[3].markdown(f'<span class="td">📞 {row["mobile"] or "—"}</span>', unsafe_allow_html=True)
                c[4].markdown(
                    f'<span class="pill {"pill-q" if is_quote else "pill-t"}">'
                    f'{"Quotation" if is_quote else "Tax Invoice"}</span>', unsafe_allow_html=True)
                c[5].markdown(f'<div class="td-amt">{float(row["total_amount"]):,.2f}</div>', unsafe_allow_html=True)
                c[6].markdown(f'<span class="td">{nice_date(row["bill_date"])}</span>', unsafe_allow_html=True)
                c[7].button("👁 View", key=f"view_{prefix}_{row['id']}", use_container_width=True,
                            on_click=open_bill, args=(int(row["id"]),))

        st.write("")
        with st.container(key="pager"):
            left, right = st.columns([5, 5], vertical_alignment="center")
            left.markdown(
                f'<div class="showing">Showing {start + 1} – {start + len(page_rows)} of {total} bills</div>',
                unsafe_allow_html=True)
            first = max(1, min(current - 2, total_pages - 5))
            numbers = list(range(first, min(total_pages, first + 5) + 1))
            with right:
                pcols = st.columns([4] + [1] * (len(numbers) + 2))
                pcols[1].button("‹", key=f"prev_{prefix}", disabled=current <= 1, use_container_width=True,
                                on_click=set_pager, args=(page_key, current - 1))
                for slot, number in zip(pcols[2:], numbers):
                    slot.button(str(number), key=f"pg_{prefix}_{number}", use_container_width=True,
                                type="primary" if number == current else "secondary",
                                on_click=set_pager, args=(page_key, number))
                pcols[-1].button("›", key=f"next_{prefix}", disabled=current >= total_pages,
                                 use_container_width=True, on_click=set_pager, args=(page_key, current + 1))

        view_id = st.session_state.get("view_bill_record_id")
        if view_id:
            record = fetch_bill_pdf(view_id)
            st.divider()
            if record:
                st.markdown(f"**📄 {record['bill_type'].title()} · {record['bill_number']}**")
                d1, d2, _ = st.columns([2, 1, 5])
                d1.download_button("⬇️ Open / Download PDF", data=bytes(record["pdf_blob"]),
                                   file_name=f"{safe_filename(record['bill_number'])}.pdf",
                                   mime="application/pdf", key=f"dl_{prefix}_{view_id}",
                                   use_container_width=True)
                d2.button("✖ Close", key=f"close_{prefix}", on_click=close_bill, use_container_width=True)
            else:
                st.warning("This bill record could not be found.")


# ============================================================
# PAGES
# ============================================================

def page_dashboard():
    render_top_header()
    selected_month = MONTHS[st.session_state.dash_month]
    previous_month = (selected_month - timedelta(days=1)).replace(day=1)
    bills = fetch_month_bills(selected_month)
    now, before = month_stats(bills), month_stats(fetch_month_bills(previous_month))

    with st.container(key="card_overview"):
        left, right = st.columns([7, 2.3], vertical_alignment="center")
        left.markdown(
            f'<div class="card-title">📅 This Month Overview '
            f'<span class="month-pill">{st.session_state.dash_month}</span></div>', unsafe_allow_html=True)
        right.selectbox("Month", MONTH_LABELS, key="dash_month", on_change=sync_from_dash,
                        label_visibility="collapsed")
        st.write("")
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi_card("blue", "📄", "Bills Generated", "(Invoices + Quotations)", now["count"],
                             pct_delta(now["count"], before["count"])), unsafe_allow_html=True)
        k2.markdown(kpi_card("green", "💰", "Total Amount", "(Tax Invoice Value)", inr(now["total"]),
                             pct_delta(now["total"], before["total"])), unsafe_allow_html=True)
        k3.markdown(kpi_card("orange", "📦", "Taxable Value", "(Before GST)", inr(now["taxable"]),
                             pct_delta(now["taxable"], before["taxable"])), unsafe_allow_html=True)
        k4.markdown(kpi_card("purple", "％", "Total GST (5%)", "(CGST 2.5% + SGST 2.5%)", inr(now["gst"]),
                             pct_delta(now["gst"], before["gst"])), unsafe_allow_html=True)

    render_bill_table("Bill Details – This Month", bills, "dash", show_month=True)


def page_history():
    render_top_header()
    render_bill_table("Bill History – All Bills", fetch_all_bills(), "hist")


def page_reports():
    render_top_header()
    with st.container(key="card_reports"):
        st.markdown('<div class="card-title">📊 Monthly Reports</div>', unsafe_allow_html=True)
        rows = fetch_monthly_summary()
        if not rows:
            st.info("No data yet. Reports appear after you generate bills.")
            return
        data = {}
        for r in rows:
            entry = data.setdefault(r["month"], {"Month": r["month"], "Tax Invoices": 0, "Quotations": 0,
                                                 "Taxable Value": 0.0, "GST": 0.0, "Total Amount": 0.0})
            if r["bill_type"] == "INVOICE":
                entry["Tax Invoices"] = r["cnt"]
                entry["Taxable Value"] = round(r["taxable"] or 0, 2)
                entry["GST"] = round(r["gst"] or 0, 2)
                entry["Total Amount"] = round(r["total"] or 0, 2)
            else:
                entry["Quotations"] = r["cnt"]
        frame = pd.DataFrame(sorted(data.values(), key=lambda e: e["Month"], reverse=True))
        st.bar_chart(frame.sort_values("Month").set_index("Month")["Total Amount"], color="#0f4fc2")
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download report (CSV)", frame.to_csv(index=False).encode("utf-8"),
                           file_name="monthly_report.csv", mime="text/csv")


def page_settings():
    render_top_header()
    with st.container(key="card_settings"):
        st.markdown('<div class="card-title">⚙️ Shop & Bank Details</div>', unsafe_allow_html=True)
        st.caption("These details are printed on every bill. Edit them at the top of app.py.")
        a, b = st.columns(2)
        a.markdown(f"**{SHOP_NAME}**\n\n{SHOP_ADDRESS.replace(chr(10), '  \n')}\n\n"
                   f"GSTIN: `{GSTIN}`\n\nMobile: {MOBILE_1} / {MOBILE_2}")
        b.markdown(f"**Bank Details**\n\nA/C Holder: {ACCOUNT_NAME}\n\nBank: {BANK_NAME}\n\n"
                   f"Account No: {ACCOUNT_NUMBER}\n\nIFSC: {IFSC}\n\nBranch: {BRANCH}")


def page_create(bill_type):
    render_top_header()
    is_invoice = bill_type == "INVOICE"
    title = "New Bill (Tax Invoice)" if is_invoice else "New Quotation"

    if "bill_number_input" not in st.session_state:
        st.session_state.bill_number_input = next_bill_number()

    # ---------- Customer + document ----------
    with st.container(key="card_customer"):
        st.markdown(f'<div class="card-title">✍️ {title}</div>', unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        with c1:
            customer_name = st.text_input("Customer Name", placeholder="Enter customer name")
            mobile = st.text_input("Mobile Number", placeholder="Enter mobile number")
        with c2:
            customer_address = st.text_area("Customer Address", placeholder="Enter customer address", height=124)
        d1, d2, d3 = st.columns(3)
        bill_number = d1.text_input("Bill / Quotation Number", key="bill_number_input")
        bill_date = d2.date_input("Date", value=date.today())
        payment_mode = d3.selectbox("Payment Mode", ["Cash", "UPI", "Bank Transfer", "Card", "Finance", "Credit"])
        if is_invoice:
            gst_rate = st.number_input("GST Rate (%)", min_value=0.0, max_value=100.0, value=5.0, step=0.5,
                                       help="Total GST. Example: 5% = CGST 2.5% + SGST 2.5%.")
            st.caption(f"Invoice GST split: CGST {gst_rate / 2:g}% + SGST {gst_rate / 2:g}%")
        else:
            gst_rate = 0.0
            st.info("Quotation: GST calculation is disabled.")

    # ---------- Add item ----------
    with st.container(key="card_item"):
        st.markdown('<div class="card-title">📦 Add Products or Services</div>', unsafe_allow_html=True)
        st.caption("Only Description and Price are required. Fill the warranty fields when the item has warranty.")
        bill_format = st.radio("Bill format", ["Spare Bill", "Bike Bill"], horizontal=True,
                               key=f"format_{bill_type.lower()}")
        description = st.text_input("Description", placeholder="Example: E-Cart Charger")
        c1, c2 = st.columns(2)
        company_name = c1.text_input("Company Name", placeholder="Example: Pelletronic")
        model_no = c2.text_input("Bike Model" if bill_format == "Bike Bill" else "Model No",
                                 placeholder="Enter bike model" if bill_format == "Bike Bill" else "Example: PPP48/15MC")
        bike_details = {}
        if bill_format == "Bike Bill":
            st.markdown("**Electric bike / scooter details**")
            row1 = st.columns(3)
            bike_details["colour"] = row1[0].text_input("Colour", placeholder="Grey")
            bike_details["chassis_no"] = row1[1].text_input("Chassis Number")
            bike_details["motor_no"] = row1[2].text_input("Motor Number")
            st.caption("Motor and controller warranty: 1 year")
            row2 = st.columns(2)
            bike_details["battery_type"] = row2[0].text_input("Battery Type", placeholder="Lithium Ion (LFP)")
            bike_details["battery_no"] = row2[1].text_input("Battery Number")
            row3 = st.columns(3)
            bike_details["battery_replacement_months"] = row3[0].number_input("Battery replacement warranty (months)", min_value=0, value=24, step=1)
            bike_details["battery_prorata_months"] = row3[1].number_input("Battery pro-rata service (months)", min_value=0, value=12, step=1)
            row4 = st.columns(3)
            bike_details["charger_name"] = row4[0].text_input("Charger Name")
            bike_details["charger_no"] = row4[1].text_input("Charger Number")
            row5 = st.columns(2)
            bike_details["charger_replacement_months"] = row5[0].number_input("Charger replacement warranty (months)", min_value=0, value=0, step=1)
            bike_details["charger_prorata_months"] = row5[1].number_input("Charger pro-rata service (months)", min_value=0, value=0, step=1)
            warranty_type_1, warranty_months_1 = "", 0
            warranty_type_2, warranty_months_2 = "", 0
        else:
            c1, c2 = st.columns(2)
            with c1:
                warranty_type_1 = st.text_input("Warranty Type 1", value="Replacement")
                warranty_months_1 = st.number_input("Warranty Type 1 - Months", min_value=0, value=3, step=1)
            with c2:
                warranty_type_2 = st.text_input("Warranty Type 2", value="Pro-rata Service")
                warranty_months_2 = st.number_input("Warranty Type 2 - Months", min_value=0, value=9, step=1)
            st.success(f"Total Warranty: **{warranty_months_1 + warranty_months_2} Months**")
        c1, c2, c3 = st.columns(3)
        hsn = c1.text_input("HSN / SAC", placeholder="Enter HSN/SAC")
        quantity = c2.number_input("Quantity", min_value=1, value=1, step=1)
        unit_price = c3.number_input("Rate / Unit Price (GST Included)", min_value=0.0, value=0.0, step=100.0)

        if st.button("➕ Add Item"):
            if not description.strip():
                st.error("Please enter the product / service description.")
            elif unit_price <= 0:
                st.error("Please enter a price greater than zero.")
            else:
                st.session_state.manual_items.append(calculate_item(
                    description.strip(), company_name.strip(), model_no.strip(),
                    warranty_type_1.strip(), warranty_months_1, warranty_type_2.strip(),
                    warranty_months_2, quantity, hsn.strip(), unit_price,
                    bill_format=bill_format, bike_details=bike_details))
                st.success(f"{description} added successfully.")

    items = list(st.session_state.manual_items)
    service_charge = 0.0
    if bill_format == "Spare Bill":
        service_charge = st.number_input("Service Charge (no quantity)", min_value=0.0, value=0.0,
                                         step=50.0, key=f"service_charge_{bill_type.lower()}")
        if service_charge > 0:
            service_item = calculate_item("Service Charge", "", "", "", 0, "", 0, 1, "", service_charge)
            service_item["no_quantity"] = True
            items.append(service_item)
    if not items:
        st.info("Add at least one product / spare / bike / charger / service.")
        return

    # ---------- Items list + edit ----------
    with st.container(key="card_items"):
        st.markdown('<div class="card-title">🛒 Items in this Bill</div>', unsafe_allow_html=True)
        st.caption("You can edit any added item before generating the PDF.")
        display = []
        for i, item in enumerate(items, start=1):
            warranty = []
            if item["warranty_type_1"] and item["warranty_months_1"] > 0:
                warranty.append(f"{item['warranty_type_1']} {item['warranty_months_1']}M")
            if item["warranty_type_2"] and item["warranty_months_2"] > 0:
                warranty.append(f"{item['warranty_type_2']} {item['warranty_months_2']}M")
            display.append({"SL": i, "Description": item["description"], "Company": item["company_name"],
                            "Model": item["model_no"], "HSN/SAC": item["hsn"], "Warranty": " + ".join(warranty),
                            "Qty": item["quantity"], "Rate": f"₹{item['unit_price']:,.2f}",
                            "Amount": f"₹{item['gross_amount']:,.2f}"})
        st.dataframe(display, use_container_width=True, hide_index=True)

        for idx, item in enumerate(items):
            if item.get("no_quantity"):
                continue
            with st.expander(f"✏️ Edit Item {idx + 1}: {item['description']}"):
                c1, c2 = st.columns(2)
                with c1:
                    e_desc = st.text_input("Description", value=item["description"], key=f"edit_desc_{idx}")
                    e_company = st.text_input("Company Name", value=item["company_name"], key=f"edit_company_{idx}")
                    e_model = st.text_input("Model No", value=item["model_no"], key=f"edit_model_{idx}")
                    e_hsn = st.text_input("HSN / SAC", value=item["hsn"], key=f"edit_hsn_{idx}")
                    e_qty = st.number_input("Quantity", min_value=1, value=int(item["quantity"]), step=1, key=f"edit_qty_{idx}")
                    e_price = st.number_input("Rate / Unit Price (GST Included)", min_value=0.0,
                                              value=float(item["unit_price"]), step=100.0, key=f"edit_price_{idx}")
                with c2:
                    e_wt1 = st.text_input("Warranty Type 1", value=item["warranty_type_1"], key=f"edit_wt1_{idx}")
                    e_wm1 = st.number_input("Warranty Type 1 - Months", min_value=0, value=int(item["warranty_months_1"]), step=1, key=f"edit_wm1_{idx}")
                    e_wt2 = st.text_input("Warranty Type 2", value=item["warranty_type_2"], key=f"edit_wt2_{idx}")
                    e_wm2 = st.number_input("Warranty Type 2 - Months", min_value=0, value=int(item["warranty_months_2"]), step=1, key=f"edit_wm2_{idx}")
                edited_bike = dict(item.get("bike_details", {}))
                if item.get("bill_format") == "Bike Bill":
                    st.caption("Bike details")
                    bike_fields = ["colour", "chassis_no", "motor_no", "battery_type", "battery_no", "charger_name", "charger_no"]
                    bike_cols = st.columns(3)
                    for field_index, field_key in enumerate(bike_fields):
                        edited_bike[field_key] = bike_cols[field_index % 3].text_input(
                            field_key.replace("_", " ").title(), value=edited_bike.get(field_key, ""), key=f"edit_bike_{field_key}_{idx}")
                    for warranty_key, label in [("battery_replacement_months", "Battery replacement months"),
                                                ("battery_prorata_months", "Battery pro-rata months"),
                                                ("charger_replacement_months", "Charger replacement months"),
                                                ("charger_prorata_months", "Charger pro-rata months")]:
                        edited_bike[warranty_key] = st.number_input(label, min_value=0,
                            value=int(edited_bike.get(warranty_key, 0)), step=1, key=f"edit_bike_{warranty_key}_{idx}")
                st.caption(f"Updated line amount preview: ₹{e_qty * e_price:,.2f}")
                b1, b2 = st.columns(2)
                if b1.button("💾 Save Item Changes", key=f"save_item_{idx}", type="primary"):
                    if not e_desc.strip() or e_price <= 0:
                        st.error("Description and a price greater than zero are required.")
                    else:
                        items[idx] = calculate_item(e_desc.strip(), e_company.strip(), e_model.strip(),
                                                    e_wt1.strip(), e_wm1, e_wt2.strip(), e_wm2,
                                                    e_qty, e_hsn.strip(), e_price,
                                                    bill_format=item.get("bill_format", "Spare Bill"),
                                                    bike_details=edited_bike)
                        st.session_state.pop("generated_pdf_bytes", None)
                        st.rerun()
                if b2.button("🗑️ Delete This Item", key=f"delete_item_{idx}"):
                    items.pop(idx)
                    st.session_state.pop("generated_pdf_bytes", None)
                    st.rerun()

    if not items:
        return

    # ---------- Summary + generate ----------
    gross_total, subtotal, cgst, sgst, rounding, grand_total = calculate_bill(items, bill_type, gst_rate)

    with st.container(key="card_summary"):
        st.markdown(f'<div class="card-title">📊 {"Invoice" if is_invoice else "Quotation"} Summary</div>',
                    unsafe_allow_html=True)
        st.write("")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Customer Total", f"₹{gross_total:,.2f}")
        if is_invoice:
            m2.metric("Taxable Subtotal", f"₹{subtotal:,.2f}")
            m3.metric(f"CGST {gst_rate / 2:g}%", f"₹{cgst:,.2f}")
            m4.metric(f"SGST {gst_rate / 2:g}%", f"₹{sgst:,.2f}")
        else:
            m2.metric("Quotation Total", f"₹{grand_total:,.2f}")
            m3.metric("GST", "Not Calculated")
            m4.metric("Document", "Quotation")
        st.success(f"### {'GRAND TOTAL' if is_invoice else 'QUOTATION TOTAL'}: ₹{grand_total:,.2f}")

        p1, p2 = st.columns(2)
        paid_amount = p1.number_input("Paid Amount", min_value=0.0, max_value=float(grand_total),
                                      value=float(grand_total), step=100.0)
        p2.markdown(f"**Balance Amount: ₹{round(grand_total - paid_amount, 2):,.2f}**")
        notes = st.text_area("Notes / Additional Details",
                             placeholder="Example: Charger warranty conditions, delivery details, special instructions, etc.")

        g1, g2 = st.columns(2)
        g1.button("🧹 Clear All Items / Start New Bill", on_click=clear_items)
        if g2.button("📄 GENERATE BILL PDF", type="primary"):
            if not customer_name.strip():
                st.error("Please enter customer name.")
            elif not bill_number.strip():
                st.error("Please enter bill / quotation number.")
            else:
                try:
                    pdf_file = create_bill_pdf(
                        bill_type=bill_type, bill_number=bill_number,
                        bill_date=bill_date.strftime("%d-%m-%Y"), customer_name=customer_name,
                        customer_address=customer_address, mobile=mobile, items=items,
                        payment_mode=payment_mode, paid_amount=paid_amount, notes=notes, gst_rate=gst_rate)
                    with open(pdf_file, "rb") as file:
                        pdf_bytes = file.read()
                    save_bill_record(
                        bill_type=bill_type, bill_number=bill_number.strip(),
                        customer_name=customer_name.strip(), mobile=mobile.strip(),
                        bill_date=bill_date.strftime("%Y-%m-%d"), total_amount=grand_total,
                        taxable_amount=subtotal if is_invoice else grand_total,
                        gst_amount=round(cgst + sgst, 2) if is_invoice else 0.0, pdf_bytes=pdf_bytes)
                    st.session_state.generated_pdf_bytes = pdf_bytes
                    st.session_state.generated_pdf_name = os.path.basename(pdf_file)
                    st.success("✅ Bill PDF generated and saved to Bill History.")
                except Exception as error:
                    st.error(f"Error while creating PDF: {error}")

        if st.session_state.get("generated_pdf_bytes"):
            st.download_button("⬇️ Download / Print Bill", data=st.session_state.generated_pdf_bytes,
                               file_name=st.session_state.get("generated_pdf_name", "bill.pdf"),
                               mime="application/pdf")
            st.caption("To correct something, edit the item above and click GENERATE BILL PDF again "
                       "(the same bill number is updated, not duplicated).")


# ============================================================
# ROUTER
# ============================================================

page = st.session_state.nav_page
if page == PAGE_DASH:
    page_dashboard()
elif page == PAGE_INVOICE:
    page_create("INVOICE")
elif page == PAGE_QUOTE:
    page_create("QUOTATION")
elif page == PAGE_HISTORY:
    page_history()
elif page == PAGE_REPORTS:
    page_reports()
else:
    page_settings()
