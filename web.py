
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

# When this app runs directly on the shop's Windows computer, save PDFs
# in the user's requested OneDrive Documents folder.
WINDOWS_BILL_FOLDER = (
    r"C:\Users\sakth\OneDrive\Documents\Sri Kabilan Motors bill format"
)

if os.name == "nt":
    BILL_FOLDER = WINDOWS_BILL_FOLDER
else:
    # Streamlit Cloud runs on a Linux server and cannot write to the
    # user's Windows C: drive. The generated PDF is still downloadable
    # through the app's Download button.
    BILL_FOLDER = os.path.join(BASE_DIR, "Bills")

os.makedirs(BILL_FOLDER, exist_ok=True)


# ============================================================
# HELPERS
