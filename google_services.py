"""
Google Services Auth Layer
Provides authenticated clients for Google Sheets and Google Docs.
"""

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CREDENTIALS_FILE = "gem-dm-ea012a4dc208.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def get_credentials():
    return Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)


def get_sheets_client():
    creds = get_credentials()
    return gspread.authorize(creds)


def get_docs_client():
    creds = get_credentials()
    return build("docs", "v1", credentials=creds)
