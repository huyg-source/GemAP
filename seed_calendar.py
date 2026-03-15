"""
seed_calendar.py
Loads Cal.csv into the calendar table.
Safe to re-run — uses upsert.

Usage:
    python seed_calendar.py
    python seed_calendar.py Cal.csv   # explicit path
"""

import csv
import os
import sys
from db_manager import init_db, upsert_calendar_day, count_calendar_days

# Shieldmeet is flagged as the leap day — it only falls on day 214
LEAP_DAY_NAME = "Shieldmeet"


def short_name(full: str) -> str:
    """Extract the short month name before any parenthetical.
    e.g. 'Hammer (Deepwinter)' -> 'Hammer'
    """
    return full.split("(")[0].strip()


def seed(path: str):
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    current_month_name  = ""
    current_month_short = ""
    seeded = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            # Pad to at least 7 columns
            while len(row) < 7:
                row.append("")

            season        = row[0].strip()
            festival_name = row[2].strip()
            day_str       = row[3].strip()
            month_cell    = row[4].strip()
            dom_str       = row[5].strip()
            notes         = row[6].strip()

            if not day_str.isdigit():
                continue   # skip blank/header rows

            day_of_year = int(day_str)

            # Month name carries forward — only populated on first day of month
            if month_cell:
                current_month_name  = month_cell
                current_month_short = short_name(month_cell)

            is_festival = 1 if festival_name else 0
            is_leap_day = 1 if LEAP_DAY_NAME.lower() in festival_name.lower() else 0

            # Festival days have no day_of_month
            day_of_month = int(dom_str) if dom_str.isdigit() else 0

            upsert_calendar_day({
                "day_of_year":   day_of_year,
                "season":        season,
                "month_name":    current_month_name,
                "month_short":   current_month_short,
                "day_of_month":  day_of_month,
                "is_festival":   is_festival,
                "is_leap_day":   is_leap_day,
                "festival_name": festival_name,
                "notes":         notes,
            })
            seeded += 1

    total = count_calendar_days()
    print(f"Seeded {seeded} days ({total} total in DB).")

    # Verify Shieldmeet was flagged
    from db_manager import get_calendar_day
    sm = next((d for d in [get_calendar_day(214)] if d), None)
    if sm and sm["is_leap_day"]:
        print(f"Shieldmeet (day 214) correctly flagged as leap day.")
    else:
        print("WARNING: Shieldmeet leap day flag not set — check Cal.csv row 214.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "Cal.csv"
    init_db()
    seed(path)
