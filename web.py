
import os
import re
import sqlite3
from datetime import date, datetime

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


# ============================================================
# SRI KABILAN MOTORS - MANUAL BILL / WARRANTY BILL
# ============================================================
#
# GST:
#   Total GST = 5%
#   CGST = 2.5%
#   SGST = 2.5%
#
# IMPORTANT:
# The rate entered by the user is GST-INCLUSIVE.
#
# Example:
# Controller = 13,795
# Motor      = 16,978
# Total      = 30,773
#
# Taxable Value = 30,773 / 1.05 = 29,307.62
# CGST 2.5%     = 732.69
# SGST 2.5%     = 732.69
# Grand Total   = 30,773.00
# ============================================================


# ============================================================
# SHOP DETAILS
# ============================================================

SHOP_NAME = "SRI KABILAN MOTORS"

SHOP_ADDRESS = (
    "NO.205/1, CUDDALORE MAIN ROAD\n"
    "HOD.OFFICE VRIDDHACHALAM-606 001\n"
    "PROINCE : MUTHANDIKUPPAM-607805\n"
    "ARIYALUR-621704"
)

GSTIN = "33AWBPV4393E2ZE"
MOBILE_1 = "8903491764"
MOBILE_2 = "9865591764"

BANK_NAME = "INDIAN BANK"
ACCOUNT_NAME = "SRI KABILAN MOTORS"
ACCOUNT_NUMBER = "669035352"
IFSC = "IDIB000V031"
BRANCH = "VRIDDHACHALAM"


# ============================================================
# GST
# ============================================================

TOTAL_GST_RATE = 5.0
CGST_RATE = 2.5
SGST_RATE = 2.5


# ============================================================
# FILE FOLDER
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BILL_FOLDER = os.path.join(BASE_DIR, "Bills")
os.makedirs(BILL_FOLDER, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def safe_filename(value):
    """Make the bill number safe for Windows filenames."""
    value = str(value).strip()
    value = re.sub(r'[\\/:*?"<>|]', "_", value)
    return value or "bill"


# ============================================================
# BILL HISTORY DATABASE
# ============================================================

DB_PATH = os.path.join(BASE_DIR, "billing_history.db")


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


def fetch_month_bills(month_value):
    month_key = month_value.strftime("%Y-%m")
    with get_db_connection() as connection:
        return connection.execute("""
            SELECT id, bill_type, bill_number, customer_name, mobile, bill_date,
                   total_amount, taxable_amount, gst_amount
            FROM bills
            WHERE substr(bill_date, 1, 7) = ?
            ORDER BY bill_date DESC, id DESC
        """, (month_key,)).fetchall()


def fetch_bill_pdf(record_id):
    with get_db_connection() as connection:
        return connection.execute(
            "SELECT bill_type, bill_number, pdf_blob FROM bills WHERE id = ?",
            (record_id,)
        ).fetchone()


initialize_database()


def number_to_words(number):
    ones = [
        "", "ONE", "TWO", "THREE", "FOUR", "FIVE",
        "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
        "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN",
        "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN",
        "NINETEEN"
    ]

    tens = [
        "", "", "TWENTY", "THIRTY", "FORTY",
        "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"
    ]

    def convert(n):
        n = int(n)

        if n < 20:
            return ones[n]

        if n < 100:
            return tens[n // 10] + (
                " " + ones[n % 10] if n % 10 else ""
            )

        if n < 1000:
            return (
                ones[n // 100]
                + " HUNDRED"
                + (" " + convert(n % 100) if n % 100 else "")
            )

        if n < 100000:
            return (
                convert(n // 1000)
                + " THOUSAND"
                + (" " + convert(n % 1000) if n % 1000 else "")
            )

        if n < 10000000:
            return (
                convert(n // 100000)
                + " LAKH"
                + (" " + convert(n % 100000) if n % 100000 else "")
            )

        return (
            convert(n // 10000000)
            + " CRORE"
            + (" " + convert(n % 10000000) if n % 10000000 else "")
        )

    number = round(float(number), 2)
    rupees = int(number)
    paise = int(round((number - rupees) * 100))

    result = convert(rupees) if rupees else "ZERO"
    result += " RUPEES"

    if paise:
        result += " AND " + convert(paise) + " PAISE"

    return result + " ONLY"


def calculate_gst_inclusive(total_inclusive, gst_rate):
    """Separate manually entered GST from a GST-inclusive price."""
    total_inclusive = round(float(total_inclusive), 2)
    gst_rate = max(float(gst_rate), 0.0)
    if gst_rate == 0:
        return total_inclusive, 0.0, 0.0, 0.0
    taxable_value = total_inclusive / (1 + gst_rate / 100)
    total_gst = total_inclusive - taxable_value
    cgst = total_gst / 2
    sgst = total_gst / 2
    taxable_value = round(taxable_value, 2)
    cgst = round(cgst, 2)
    sgst = round(sgst, 2)
    rounding = round(total_inclusive - (taxable_value + cgst + sgst), 2)
    return taxable_value, cgst, sgst, rounding


def calculate_item(description, company_name, model_no, warranty_type_1,
                   warranty_months_1, warranty_type_2, warranty_months_2,
                   quantity, hsn, unit_price):
    gross_amount = round(quantity * unit_price, 2)
    return {
        "description": description,
        "company_name": company_name,
        "model_no": model_no,
        "warranty_type_1": warranty_type_1,
        "warranty_months_1": warranty_months_1,
        "warranty_type_2": warranty_type_2,
        "warranty_months_2": warranty_months_2,
        "quantity": quantity,
        "hsn": hsn,
        "unit_price": unit_price,
        "gross_amount": gross_amount,
    }


def calculate_bill(items, bill_type, gst_rate):
    """Quotation: no GST. Invoice: GST-inclusive prices with manual GST rate."""
    gross_total = round(sum(item["gross_amount"] for item in items), 2)
    if bill_type == "QUOTATION":
        return gross_total, gross_total, 0.0, 0.0, 0.0, gross_total

    subtotal = cgst = sgst = 0.0
    for item in items:
        taxable, item_cgst, item_sgst, _ = calculate_gst_inclusive(
            item["gross_amount"], gst_rate
        )
        subtotal += taxable
        cgst += item_cgst
        sgst += item_sgst
    subtotal = round(subtotal, 2)
    cgst = round(cgst, 2)
    sgst = round(sgst, 2)
    rounding = round(gross_total - subtotal - cgst - sgst, 2)
    grand_total = round(subtotal + cgst + sgst + rounding, 2)
    return gross_total, subtotal, cgst, sgst, rounding, grand_total


def warranty_text(item):
    parts = []

    if item["warranty_type_1"].strip() and item["warranty_months_1"] > 0:
        parts.append(
            f"{item['warranty_type_1'].strip()} warranty - "
            f"{item['warranty_months_1']} months"
        )

    if item["warranty_type_2"].strip() and item["warranty_months_2"] > 0:
        parts.append(
            f"{item['warranty_type_2'].strip()} warranty - "
            f"{item['warranty_months_2']} months"
        )

    if parts:
        total_months = (
            item["warranty_months_1"]
            + item["warranty_months_2"]
        )
        parts.append(f"Total Warranty - {total_months} months")

    return "<br/>".join(parts)


# ============================================================
# PDF
# ============================================================

def create_bill_pdf(
    bill_type,
    bill_number,
    bill_date,
    customer_name,
    customer_address,
    mobile,
    items,
    payment_mode,
    paid_amount,
    notes,
    gst_rate,
):
    safe_number = safe_filename(bill_number)

    filename = os.path.join(
        BILL_FOLDER,
        f"{bill_type.lower()}_{safe_number}.pdf"
    )

    (
        gross_total,
        subtotal,
        cgst,
        sgst,
        rounding,
        grand_total,
    ) = calculate_bill(items, bill_type, gst_rate)

    balance = round(
        grand_total - paid_amount,
        2
    )

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "BillTitle",
        parent=styles["Normal"],
        fontSize=12,
        leading=14,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    normal_style = ParagraphStyle(
        "BillNormal",
        parent=styles["Normal"],
        fontSize=8.2,
        leading=10,
    )

    small_style = ParagraphStyle(
        "BillSmall",
        parent=normal_style,
        fontSize=7.5,
        leading=9,
    )

    center_style = ParagraphStyle(
        "BillCenter",
        parent=normal_style,
        alignment=TA_CENTER,
    )

    right_style = ParagraphStyle(
        "BillRight",
        parent=normal_style,
        alignment=TA_RIGHT,
    )

    elements = []

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    elements.append(
        Paragraph(bill_type.upper(), title_style)
    )
    elements.append(Spacer(1, 2 * mm))

    # --------------------------------------------------------
    # SHOP HEADER
    # --------------------------------------------------------

    shop_text = (
        f"<b>{SHOP_NAME}</b><br/>"
        + SHOP_ADDRESS.replace("\n", "<br/>")
    )

    contact_text = (
        f"<b>GSTIN/UIN : {GSTIN}</b><br/>"
        f"<b>MOB NO : {MOBILE_1}</b><br/>"
        f"{MOBILE_2}"
    )

    header = Table(
        [[
            Paragraph(shop_text, normal_style),
            Paragraph(contact_text, right_style),
        ]],
        colWidths=[108 * mm, 67 * mm],
    )

    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(header)

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    customer_text = (
        f"<b>Customer: {customer_name}</b><br/>"
        f"Mobile: {mobile}<br/>"
        + customer_address.replace("\n", "<br/>")
    )

    document_text = (
        f"<b>{bill_type} NO : {bill_number}</b><br/>"
        f"<b>DATE : {bill_date}</b>"
    )

    customer_table = Table(
        [[
            Paragraph(customer_text, normal_style),
            Paragraph(document_text, right_style),
        ]],
        colWidths=[108 * mm, 67 * mm],
    )

    customer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(customer_table)
    elements.append(Spacer(1, 2 * mm))

    # --------------------------------------------------------
    # ITEM TABLE
    # Includes company, model and warranty details.
    # --------------------------------------------------------

    table_data = [[
        Paragraph("<b>SL<br/>NO</b>", center_style),
        Paragraph("<b>DESCRIPTION / PRODUCT DETAILS</b>", center_style),
        Paragraph("<b>HSN/<br/>SAC</b>", center_style),
        Paragraph("<b>QTY</b>", center_style),
        Paragraph("<b>RATE<br/>(GST INCL.)</b>", center_style),
        Paragraph("<b>AMOUNT<br/>(GST INCL.)</b>", center_style),
    ]]

    for index, item in enumerate(items, start=1):

        details = (
            f"<b>{item['description']}</b>"
        )

        if item["company_name"].strip():
            details += (
                f"<br/><b>Company:</b> "
                f"{item['company_name']}"
            )

        if item["model_no"].strip():
            details += (
                f"<br/><b>Model No:</b> "
                f"{item['model_no']}"
            )

        warranty = warranty_text(item)

        if warranty:
            details += (
                f"<br/><b>Warranty:</b><br/>"
                f"{warranty}"
            )

        table_data.append([
            str(index),
            Paragraph(details, small_style),
            item["hsn"],
            str(item["quantity"]),
            f"{item['unit_price']:,.2f}",
            f"{item['gross_amount']:,.2f}",
        ])

    # Keep a reasonable number of blank rows.
    # IMPORTANT:
    # Do not force too many rows here. Too many blank rows can push
    # the totals/signature section onto page 2 even when there is
    # only one product.
    #
    # Header + 7 rows = 8 rows total.
    # If there are many products, ReportLab can continue the table
    # onto the next page naturally.
    while len(table_data) < 8:
        table_data.append([
            "",
            Spacer(1, 7 * mm),
            "",
            "",
            "",
            "",
        ])

    item_table = Table(
        table_data,
        colWidths=[
            9 * mm,
            78 * mm,
            19 * mm,
            15 * mm,
            27 * mm,
            27 * mm,
        ],
        repeatRows=1,
        splitByRow=1,
    )

    item_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    elements.append(item_table)

    # --------------------------------------------------------
    # GST / TOTAL SUMMARY
    if bill_type == "QUOTATION":
        totals_data = [["", "", "", "TOTAL", f"{grand_total:,.2f}"]]
    else:
        cgst_rate = gst_rate / 2
        sgst_rate = gst_rate / 2
        totals_data = [
            ["", "", "", "TAXABLE SUBTOTAL", f"{subtotal:,.2f}"],
            ["", "", "", f"CGST @ {cgst_rate:g}%", f"{cgst:,.2f}"],
            ["", "", "", f"SGST @ {sgst_rate:g}%", f"{sgst:,.2f}"],
        ]
        if rounding != 0:
            totals_data.append(["", "", "", "ROUNDING", f"{rounding:,.2f}"])
        totals_data.append(["", "", "", "GRAND TOTAL", f"{grand_total:,.2f}"])

    totals_table = Table(
        totals_data,
        colWidths=[9 * mm, 78 * mm, 19 * mm, 49 * mm, 20 * mm],
    )
    totals_table.setStyle(TableStyle([
        ("GRID", (3, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (3, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (3, 0), (-1, -1), 8.0),
        ("TOPPADDING", (3, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (3, 0), (-1, -1), 4),
    ]))
    elements.append(totals_table)

    # AMOUNT IN WORDS
    # --------------------------------------------------------

    words_table = Table(
        [[
            Paragraph(
                f"<b>Amount in Words : "
                f"{number_to_words(grand_total)}</b>",
                normal_style,
            )
        ]],
        colWidths=[175 * mm],
    )

    words_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(words_table)

    # --------------------------------------------------------
    # PAYMENT
    # --------------------------------------------------------

    payment_text = (
        f"<b>Payment Mode : {payment_mode}</b><br/>"
        f"Paid Amount : ₹{paid_amount:,.2f}<br/>"
        f"Balance Amount : ₹{balance:,.2f}"
    )

    payment_table = Table(
        [[Paragraph(payment_text, normal_style)]],
        colWidths=[175 * mm],
    )

    payment_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(payment_table)

    # --------------------------------------------------------
    # BANK DETAILS
    # --------------------------------------------------------

    bank_text = (
        f"<b>Bank Details:</b><br/>"
        f"A/C Holder Name : {ACCOUNT_NAME}<br/>"
        f"Company Bank Name : {BANK_NAME}<br/>"
        f"Account No : {ACCOUNT_NUMBER}<br/>"
        f"IFSC CODE : {IFSC}<br/>"
        f"BRANCH : {BRANCH}"
    )

    bank_table = Table(
        [[Paragraph(bank_text, normal_style)]],
        colWidths=[175 * mm],
    )

    bank_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(bank_table)

    # --------------------------------------------------------
    # TERMS + SIGNATURE
    # --------------------------------------------------------

    notes_text = (
        "<b>TERMS & CONDITIONS E. & O.E.</b><br/>"
        "1. Goods once cannot be taken back.<br/>"
        "2. Payment as agreed.<br/>"
        "3. E. & O.E."
    )

    if notes.strip():
        notes_text += (
            "<br/><b>Notes:</b> "
            + notes.replace("\n", "<br/>")
        )

    # Bottom section:
    # - Terms on the left
    # - "For SRI KABILAN MOTORS" on the right
    # - Customer Signature at bottom-left
    # - Authorised Signatory at bottom-right
    terms_and_signatures = Table(
        [
            [
                Paragraph(notes_text, normal_style),
                Paragraph(
                    f"<b>For {SHOP_NAME}</b>",
                    right_style,
                ),
            ],
            [
                "",
                "",
            ],
            [
                Paragraph(
                    "<b>Customer Signature</b>",
                    normal_style,
                ),
                Paragraph(
                    "<b>Authorised Signatory</b>",
                    right_style,
                ),
            ],
        ],
        colWidths=[87.5 * mm, 87.5 * mm],
        # Compact enough to remain on page 1 for a normal one-item bill.
        rowHeights=[18 * mm, 10 * mm, 10 * mm],
    )

    terms_and_signatures.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 2), (-1, 2), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 2), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(terms_and_signatures)
    elements.append(Spacer(1, 2 * mm))

    elements.append(
        Paragraph(
            "<b>This is a Computer Generated Bill</b>",
            center_style,
        )
    )

    doc.build(elements)

    return filename


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Sri Kabilan Motors | Billing Suite",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Professional application styling (Streamlit-native; no extra packages).
st.markdown("""
<style>
    :root { --brand: #123b5d; --brand2: #1d6585; --ink: #172b3a; --muted: #647789; }
    .stApp { background: #f4f7fb; color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(244,247,251,.92); }
    .block-container { max-width: 1440px; padding-top: 1.5rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #102f49; }
    [data-testid="stSidebar"] * { color: #f4f8fc !important; }
    .brand-header { background: linear-gradient(115deg,#102f49 0%,#1d6585 100%); padding: 25px 30px; border-radius: 18px; color: white; margin-bottom: 18px; box-shadow: 0 8px 24px rgba(16,47,73,.14); }
    .brand-header h1 { color: white; font-size: 30px; margin: 0 0 5px 0; font-weight: 750; letter-spacing: .2px; }
    .brand-header p { color: #dceaf4; margin: 0; font-size: 14px; }
    .section-kicker { color: #1d6585; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.1px; margin: 4px 0 3px; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #e3eaf1; padding: 15px 17px; border-radius: 13px; box-shadow: 0 3px 12px rgba(20,48,70,.04); }
    div[data-testid="stMetricLabel"] { color: #647789; }
    div[data-testid="stMetricValue"] { color: #123b5d; font-weight: 750; }
    div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button { border-radius: 9px; min-height: 42px; font-weight: 650; border: 1px solid #d7e2eb; }
    div[data-testid="stButton"] > button[kind="primary"] { background: #15577b; border-color: #15577b; }
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea { border-radius: 8px; }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-radius: 8px; }
    [data-testid="stExpander"] { background: white; border: 1px solid #e3eaf1; border-radius: 12px; }
    [data-testid="stDataFrame"] { border: 1px solid #e3eaf1; border-radius: 10px; overflow: hidden; }
    hr { border-color: #e2eaf1; }
    .helper-text { color: #647789; font-size: 13px; }
    @media (max-width: 700px) {
      .block-container { padding: 1rem .8rem 2rem; }
      .brand-header { padding: 20px; border-radius: 13px; }
      .brand-header h1 { font-size: 23px; }
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🛵 SRI KABILAN MOTORS")
    st.caption("BILLING & DOCUMENT MANAGEMENT")
    st.divider()
    st.markdown("**Application**")
    st.markdown("🧾 Invoice generation")
    st.markdown("📄 Quotation generation")
    st.markdown("📦 Product & warranty details")
    st.markdown("⬇️ PDF download")
    st.divider()
    st.markdown("**Business details**")
    st.caption(f"GSTIN: {GSTIN}")
    st.caption(f"Phone: {MOBILE_1} / {MOBILE_2}")
    st.divider()
    st.caption("Sri Kabilan Motors Billing Suite")
    st.caption("Version 2.0 · Streamlit")

st.markdown(
    '<div class="brand-header"><h1>🛵 SRI KABILAN MOTORS</h1>'
    '<p>Professional Billing Suite · Invoices, quotations and bill history.</p></div>',
    unsafe_allow_html=True,
)

# Top-right document shortcuts
left_space, quotation_col, invoice_col = st.columns([6, 2, 2])
with quotation_col:
    if st.button("📄 Quotation", use_container_width=True):
        st.session_state.selected_bill_type = "QUOTATION"
        st.session_state.document_type_selector = "QUOTATION"
        st.rerun()
with invoice_col:
    if st.button("＋ New Bill (Tax Invoice)", type="primary", use_container_width=True):
        st.session_state.selected_bill_type = "INVOICE"
        st.session_state.document_type_selector = "INVOICE"
        st.rerun()

# Monthly dashboard
st.markdown("## 📊 This Month Overview")
month_col, _ = st.columns([2, 5])
with month_col:
    report_month = st.date_input(
        "Select month",
        value=date.today().replace(day=1),
        help="Choose any date in the month you want to review.",
        key="dashboard_report_month",
    )
month_bills = fetch_month_bills(report_month)
month_invoice = [row for row in month_bills if row["bill_type"] == "INVOICE"]
month_quotation = [row for row in month_bills if row["bill_type"] == "QUOTATION"]
month_total = sum(float(row["total_amount"] or 0) for row in month_invoice)
month_taxable = sum(float(row["taxable_amount"] or 0) for row in month_invoice)
month_gst = sum(float(row["gst_amount"] or 0) for row in month_invoice)
metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Bills Generated", len(month_invoice))
metric2.metric("Total Invoice Amount", f"₹{month_total:,.2f}")
metric3.metric("Taxable Value", f"₹{month_taxable:,.2f}")
metric4.metric("Total GST", f"₹{month_gst:,.2f}")
st.caption(f"Also generated: {len(month_quotation)} quotation(s) · Amounts above include tax invoices only.")

# Bill history table
st.markdown("## 🧾 Bill Details – This Month")
search_bill = st.text_input(
    "Search bills",
    placeholder="Search by bill number, customer name or phone number...",
    key="bill_history_search",
)
filtered_bills = [row for row in month_bills if (
    search_bill.strip().lower() in " ".join([
        str(row["bill_number"] or ""), str(row["customer_name"] or ""),
        str(row["mobile"] or "")
    ]).lower()
)] if search_bill.strip() else month_bills

if filtered_bills:
    header_cols = st.columns([0.45, 1.15, 1.45, 1.2, 1.0, 1.0, 0.85])
    for header_col, heading in zip(header_cols, ["#", "Bill No", "Customer Name", "Phone No", "Bill Type", "Amount (₹)", "Action"]):
        header_col.markdown(f"**{heading}**")
    st.divider()
    for row in filtered_bills:
        row_cols = st.columns([0.45, 1.15, 1.45, 1.2, 1.0, 1.0, 0.85])
        row_cols[0].write(str(row["id"]))
        row_cols[1].write(str(row["bill_number"]))
        row_cols[2].write(str(row["customer_name"]))
        row_cols[3].write(str(row["mobile"] or "—"))
        row_cols[4].write("Quotation" if row["bill_type"] == "QUOTATION" else "Tax Invoice")
        row_cols[5].write(f'₹{float(row["total_amount"]):,.2f}')
        if row_cols[6].button("👁 View", key=f'view_bill_{row["id"]}', use_container_width=True):
            st.session_state.view_bill_record_id = int(row["id"])
    st.caption(f"Showing {len(filtered_bills)} of {len(month_bills)} document(s) for {report_month.strftime('%B %Y')}.")
else:
    st.info("No bills or quotations found for this month yet. Generated documents will appear here.")

if st.session_state.get("view_bill_record_id"):
    viewed_record = fetch_bill_pdf(st.session_state.view_bill_record_id)
    if viewed_record:
        st.markdown("### 📄 Selected bill")
        st.caption(f'{viewed_record["bill_type"].title()} · {viewed_record["bill_number"]}')
        st.download_button(
            "⬇️ Download / View PDF",
            data=bytes(viewed_record["pdf_blob"]),
            file_name=f'{safe_filename(viewed_record["bill_number"])}.pdf',
            mime="application/pdf",
            key=f'download_viewed_{st.session_state.view_bill_record_id}',
        )
    else:
        st.warning("This bill record could not be found.")

st.divider()
st.markdown("## ✍️ Create a Document")
st.info(
    "Choose Quotation or New Bill (Tax Invoice) from the top-right buttons. "
    "Add products, review or edit them, then generate the PDF."
)

# ============================================================
# GST EXAMPLE
# ============================================================

with st.expander("📌 GST Calculation Example"):
    st.write("Invoice: enter GST percentage manually.")
    st.write("Example: GST 5% = CGST 2.5% + SGST 2.5%.")
    st.write("Controller = ₹13,795")
    st.write("Motor = ₹16,978")
    st.write("Customer Total = ₹30,773")
    st.write("Taxable Subtotal = ₹29,307.62")
    st.write("CGST @ 2.5% = ₹732.69")
    st.write("SGST @ 2.5% = ₹732.69")
    st.write("Grand Total = ₹30,773.00")
    st.write("Quotation: GST is not calculated.")


# ============================================================
# CUSTOMER DETAILS
# ============================================================

st.markdown("### 👤 Customer information")
st.caption("Enter the customer details that will appear on the bill.")

col1, col2 = st.columns(2)

with col1:
    customer_name = st.text_input(
        "Customer Name",
        placeholder="Enter customer name",
    )

    mobile = st.text_input(
        "Mobile Number",
        placeholder="Enter mobile number",
    )

with col2:
    customer_address = st.text_area(
        "Customer Address",
        placeholder="Enter customer address",
    )

    bill_date = st.date_input(
        "Date",
        value=date.today(),
    )


# ============================================================
# BILL DETAILS
# ============================================================

st.markdown("### 🧾 Document settings")
st.caption("Choose the document type, number, date and payment method.")

col1, col2, col3 = st.columns(3)

with col1:
    if "selected_bill_type" not in st.session_state:
        st.session_state.selected_bill_type = "INVOICE"
    bill_type = st.selectbox(
        "Bill Type",
        ["INVOICE", "QUOTATION"],
        index=0 if st.session_state.selected_bill_type == "INVOICE" else 1,
        format_func=lambda value: "Tax Invoice" if value == "INVOICE" else "Quotation",
        key="document_type_selector",
    )
    st.session_state.selected_bill_type = bill_type

with col2:
    bill_number = st.text_input(
        "Bill / Quotation Number",
        value="40/2026",
    )

with col3:
    payment_mode = st.selectbox(
        "Payment Mode",
        [
            "Cash",
            "UPI",
            "Bank Transfer",
            "Card",
            "Finance",
            "Credit",
        ],
    )

if bill_type == "INVOICE":
    gst_rate = st.number_input(
        "GST Rate (%)",
        min_value=0.0,
        max_value=100.0,
        value=5.0,
        step=0.5,
        help="Enter total GST. Example: 5% = CGST 2.5% + SGST 2.5%.",
    )
    st.caption(
        f"Invoice GST split: CGST {gst_rate / 2:g}% + SGST {gst_rate / 2:g}%"
    )
else:
    gst_rate = 0.0
    st.info("Quotation: GST calculation is disabled.")


# ============================================================
# ITEM ENTRY
# ============================================================

st.markdown("### 📦 Add products or services")
st.caption("Enter each product manually. Add multiple items to the same invoice or quotation.")

st.caption(
    "All fields are optional except Description and Price. "
    "Use the warranty fields when the item has warranty."
)

description = st.text_input(
    "Description",
    placeholder="Example: E-Cart Charger",
)

col1, col2 = st.columns(2)

with col1:
    company_name = st.text_input(
        "Company Name",
        placeholder="Example: Pelletronic",
    )

with col2:
    model_no = st.text_input(
        "Model No",
        placeholder="Example: PPP48/15MC",
    )

st.subheader("Warranty Details")

col1, col2 = st.columns(2)

with col1:
    warranty_type_1 = st.text_input(
        "Warranty Type 1",
        value="Replacement",
        placeholder="Example: Replacement",
    )

    warranty_months_1 = st.number_input(
        "Warranty Type 1 - Months",
        min_value=0,
        value=3,
        step=1,
    )

with col2:
    warranty_type_2 = st.text_input(
        "Warranty Type 2",
        value="Pro-rata Service",
        placeholder="Example: Pro-rata Service",
    )

    warranty_months_2 = st.number_input(
        "Warranty Type 2 - Months",
        min_value=0,
        value=9,
        step=1,
    )

total_warranty_months = (
    warranty_months_1 + warranty_months_2
)

st.success(
    f"Total Warranty: **{total_warranty_months} Months**"
)

col1, col2, col3 = st.columns(3)

with col1:
    hsn = st.text_input(
        "HSN / SAC",
        placeholder="Enter HSN/SAC",
    )

with col2:
    quantity = st.number_input(
        "Quantity",
        min_value=1,
        value=1,
        step=1,
    )

with col3:
    unit_price = st.number_input(
        "Rate / Unit Price (GST Included)",
        min_value=0.0,
        value=0.0,
        step=100.0,
    )


# ============================================================
# SESSION ITEMS
# ============================================================

if "manual_items" not in st.session_state:
    st.session_state.manual_items = []


if st.button("➕ Add Item", type="secondary"):

    if not description.strip():
        st.error(
            "Please enter the product / service description."
        )

    elif unit_price <= 0:
        st.error(
            "Please enter a price greater than zero."
        )

    else:
        item = calculate_item(
            description=description.strip(),
            company_name=company_name.strip(),
            model_no=model_no.strip(),
            warranty_type_1=warranty_type_1.strip(),
            warranty_months_1=warranty_months_1,
            warranty_type_2=warranty_type_2.strip(),
            warranty_months_2=warranty_months_2,
            quantity=quantity,
            hsn=hsn.strip(),
            unit_price=unit_price,
        )

        st.session_state.manual_items.append(item)

        st.success(
            f"{description} added successfully."
        )


# ============================================================
# DISPLAY + EDIT ITEMS
# ============================================================

if st.session_state.manual_items:
    st.markdown("### 🛒 Items in this bill")
    st.caption("You can edit any added item before generating the PDF.")

    display_data = []
    for i, item in enumerate(st.session_state.manual_items, start=1):
        warranty = []
        if item["warranty_type_1"] and item["warranty_months_1"] > 0:
            warranty.append(f"{item['warranty_type_1']} {item['warranty_months_1']}M")
        if item["warranty_type_2"] and item["warranty_months_2"] > 0:
            warranty.append(f"{item['warranty_type_2']} {item['warranty_months_2']}M")
        display_data.append({
            "SL": i, "Description": item["description"],
            "Company": item["company_name"], "Model": item["model_no"],
            "HSN/SAC": item["hsn"], "Warranty": " + ".join(warranty),
            "Qty": item["quantity"], "Rate": f"₹{item['unit_price']:,.2f}",
            "Amount": f"₹{item['gross_amount']:,.2f}",
        })
    st.dataframe(display_data, use_container_width=True, hide_index=True)

    for idx, item in enumerate(st.session_state.manual_items):
        with st.expander(f"✏️ Edit Item {idx + 1}: {item['description']}"):
            c1, c2 = st.columns(2)
            with c1:
                e_desc = st.text_input("Description", value=item["description"], key=f"edit_desc_{idx}")
                e_company = st.text_input("Company Name", value=item["company_name"], key=f"edit_company_{idx}")
                e_model = st.text_input("Model No", value=item["model_no"], key=f"edit_model_{idx}")
                e_hsn = st.text_input("HSN / SAC", value=item["hsn"], key=f"edit_hsn_{idx}")
                e_qty = st.number_input("Quantity", min_value=1, value=int(item["quantity"]), step=1, key=f"edit_qty_{idx}")
                e_price = st.number_input("Rate / Unit Price (GST Included)", min_value=0.0, value=float(item["unit_price"]), step=100.0, key=f"edit_price_{idx}")
            with c2:
                e_wt1 = st.text_input("Warranty Type 1", value=item["warranty_type_1"], key=f"edit_wt1_{idx}")
                e_wm1 = st.number_input("Warranty Type 1 - Months", min_value=0, value=int(item["warranty_months_1"]), step=1, key=f"edit_wm1_{idx}")
                e_wt2 = st.text_input("Warranty Type 2", value=item["warranty_type_2"], key=f"edit_wt2_{idx}")
                e_wm2 = st.number_input("Warranty Type 2 - Months", min_value=0, value=int(item["warranty_months_2"]), step=1, key=f"edit_wm2_{idx}")
            st.caption(f"Updated line amount preview: ₹{e_qty * e_price:,.2f}")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 Save Item Changes", key=f"save_item_{idx}", type="primary"):
                    if not e_desc.strip() or e_price <= 0:
                        st.error("Description and a price greater than zero are required.")
                    else:
                        st.session_state.manual_items[idx] = calculate_item(
                            description=e_desc.strip(), company_name=e_company.strip(),
                            model_no=e_model.strip(), warranty_type_1=e_wt1.strip(),
                            warranty_months_1=e_wm1, warranty_type_2=e_wt2.strip(),
                            warranty_months_2=e_wm2, quantity=e_qty, hsn=e_hsn.strip(),
                            unit_price=e_price,
                        )
                        st.session_state.pop("generated_pdf_bytes", None)
                        st.success("Item updated. Generate the PDF again to apply the changes.")
                        st.rerun()
            with b2:
                if st.button("🗑️ Delete This Item", key=f"delete_item_{idx}"):
                    st.session_state.manual_items.pop(idx)
                    st.session_state.pop("generated_pdf_bytes", None)
                    st.rerun()


# ============================================================
# TOTALS
# ============================================================

if st.session_state.manual_items:

    (
        gross_total,
        subtotal,
        cgst,
        sgst,
        rounding,
        grand_total,
    ) = calculate_bill(
        st.session_state.manual_items,
        bill_type,
        gst_rate,
    )

    if bill_type == "INVOICE":
        st.markdown("### 📊 Invoice summary")
    else:
        st.markdown("### 📊 Quotation summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Customer Total", f"₹{gross_total:,.2f}")

    if bill_type == "INVOICE":
        with col2:
            st.metric("Taxable Subtotal", f"₹{subtotal:,.2f}")
        with col3:
            st.metric(f"CGST {gst_rate / 2:g}%", f"₹{cgst:,.2f}")
        with col4:
            st.metric(f"SGST {gst_rate / 2:g}%", f"₹{sgst:,.2f}")
    else:
        with col2:
            st.metric("Quotation Total", f"₹{grand_total:,.2f}")
        with col3:
            st.metric("GST", "Not Calculated")
        with col4:
            st.metric("Document", "Quotation")

    st.success(
        f"### {'GRAND TOTAL' if bill_type == 'INVOICE' else 'QUOTATION TOTAL'}: ₹{grand_total:,.2f}"
    )

    paid_amount = st.number_input(
        "Paid Amount",
        min_value=0.0,
        max_value=float(grand_total),
        value=float(grand_total),
        step=100.0,
    )

    balance = round(
        grand_total - paid_amount,
        2
    )

    st.write(
        f"**Balance Amount: ₹{balance:,.2f}**"
    )

    notes = st.text_area(
        "Notes / Additional Details",
        placeholder=(
            "Example: Charger warranty conditions, "
            "delivery details, special instructions, etc."
        ),
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🧹 Clear All Items"):
            st.session_state.manual_items = []
            st.session_state.pop("generated_pdf_bytes", None)
            st.rerun()

    with col2:
        if st.button(
            "📄 GENERATE BILL PDF",
            type="primary",
        ):

            if not customer_name.strip():
                st.error(
                    "Please enter customer name."
                )

            elif not bill_number.strip():
                st.error(
                    "Please enter bill / quotation number."
                )

            else:
                try:
                    pdf_file = create_bill_pdf(
                        bill_type=bill_type,
                        bill_number=bill_number,
                        bill_date=bill_date.strftime(
                            "%d-%m-%Y"
                        ),
                        customer_name=customer_name,
                        customer_address=customer_address,
                        mobile=mobile,
                        items=st.session_state.manual_items,
                        payment_mode=payment_mode,
                        paid_amount=paid_amount,
                        notes=notes,
                        gst_rate=gst_rate,
                    )

                    st.success(
                        "✅ Bill PDF generated successfully!"
                    )

                    with open(pdf_file, "rb") as file:
                        pdf_bytes = file.read()

                    saved_taxable = subtotal if bill_type == "INVOICE" else grand_total
                    saved_gst = round(cgst + sgst, 2) if bill_type == "INVOICE" else 0.0
                    save_bill_record(
                        bill_type=bill_type,
                        bill_number=bill_number.strip(),
                        customer_name=customer_name.strip(),
                        mobile=mobile.strip(),
                        bill_date=bill_date.strftime("%Y-%m-%d"),
                        total_amount=grand_total,
                        taxable_amount=saved_taxable,
                        gst_amount=saved_gst,
                        pdf_bytes=pdf_bytes,
                    )
                    st.session_state.generated_pdf_bytes = pdf_bytes
                    st.session_state.generated_pdf_name = os.path.basename(pdf_file)

                    st.download_button(
                        label="⬇️ Download / Print Bill",
                        data=pdf_bytes,
                        file_name=os.path.basename(
                            pdf_file
                        ),
                        mime="application/pdf",
                    )
                    st.caption("Need to correct an item or price? Use the Edit Item section above, save the change, then click GENERATE BILL PDF again. The PDF file itself is a final document; edits are made here and a fresh PDF is generated.")

                    st.success("Bill details and PDF saved to bill history on this app instance.")
                    st.caption("Use the Bill Details section above to find and download this document later.")

                except Exception as error:
                    st.error(
                        f"Error while creating PDF: {error}"
                    )

else:
    st.info(
        "Add at least one product / spare / bike / charger / service."
    )


if st.session_state.get("generated_pdf_bytes"):
    st.divider()
    st.info("A bill PDF has already been generated in this session. If you edit or delete an item, generate the PDF again so the downloaded copy includes the latest changes.")
