
import os
import re
from datetime import date

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
    page_title="Sri Kabilan Motors Bill",
    page_icon="🛵",
    layout="wide",
)

st.title("🛵 SRI KABILAN MOTORS")
st.subheader("Manual Bill / Quotation Generator")

st.info(
    "Enter any bike, charger, motor, controller, spare part or service. "
    "Invoice = manual GST calculation. Quotation = no GST calculation."
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

st.header("Customer Details")

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

st.header("Bill Details")

col1, col2, col3 = st.columns(3)

with col1:
    bill_type = st.selectbox(
        "Bill Type",
        ["QUOTATION", "INVOICE"],
    )

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

st.header("Product / Spare / Bike / Charger Details")

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
# DISPLAY ITEMS
# ============================================================

if st.session_state.manual_items:

    st.header("Added Items")

    display_data = []

    for i, item in enumerate(
        st.session_state.manual_items,
        start=1,
    ):

        warranty = []

        if (
            item["warranty_type_1"]
            and item["warranty_months_1"] > 0
        ):
            warranty.append(
                f"{item['warranty_type_1']} "
                f"{item['warranty_months_1']}M"
            )

        if (
            item["warranty_type_2"]
            and item["warranty_months_2"] > 0
        ):
            warranty.append(
                f"{item['warranty_type_2']} "
                f"{item['warranty_months_2']}M"
            )

        display_data.append({
            "SL": i,
            "Description": item["description"],
            "Company": item["company_name"],
            "Model": item["model_no"],
            "Warranty": " + ".join(warranty),
            "Qty": item["quantity"],
            "Rate": f"₹{item['unit_price']:,.2f}",
            "Amount": f"₹{item['gross_amount']:,.2f}",
        })

    st.dataframe(
        display_data,
        use_container_width=True,
        hide_index=True,
    )

    remove_number = st.number_input(
        "Enter SL NO to remove (0 = don't remove)",
        min_value=0,
        max_value=len(st.session_state.manual_items),
        value=0,
        step=1,
    )

    if st.button("🗑️ Remove Selected Item"):
        if remove_number > 0:
            st.session_state.manual_items.pop(
                remove_number - 1
            )
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
        st.header("Invoice GST Calculation")
    else:
        st.header("Quotation Total")

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

                    st.download_button(
                        label="⬇️ Download / Print Bill",
                        data=pdf_bytes,
                        file_name=os.path.basename(
                            pdf_file
                        ),
                        mime="application/pdf",
                    )

                    st.info(
                        f"PDF saved in: {BILL_FOLDER}"
                    )

                except Exception as error:
                    st.error(
                        f"Error while creating PDF: {error}"
                    )

else:
    st.info(
        "Add at least one product / spare / bike / charger / service."
    )
