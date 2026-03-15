"""
seed_spells_csv.py
Imports spells from a CSV exported from your Google Sheet Spells tab.

Two things happen in one pass:
  1. Any spell not already in spells_reference is added (reference top-up).
  2. If --char-name and --campaign-id are given, Spellbook/Discovered/Prepare
     columns are used to populate that character's character_spellbook rows.

Usage:
    # Inspect columns first:
    python seed_spells_csv.py spells.csv --show-columns

    # Reference top-up only (no character import):
    python seed_spells_csv.py spells.csv --source "PHB"

    # Reference + character spellbook:
    python seed_spells_csv.py spells.csv --default-source "PHB" --char-name "Demo" --campaign-id 0

    # With a specific source per row (if your CSV has a Source column):
    python seed_spells_csv.py spells.csv --default-source "PHB"

Your sheet headers (detected automatically):
    Level         → level
    Name          → name  (required)
    Ritual        → ritual
    Concentration → concentration
    ClassRestrict → classes
    Save Type     → save_type  (duplicate handled — first column wins)
    Components    → components
    Casting Time  → casting_time
    Range         → range
    Duration      → duration
    Source        → source  (overrides --default-source if present)
    Spellbook     → character: which spellbook/character has this spell
    Discovered    → character: has the character found this spell
    Prepare       → character: is it prepared
"""

import sys
import csv
import argparse
from db_manager import (
    init_db, upsert_spell_reference, count_spells_reference,
    add_to_spellbook, search_spells_reference,
)

# ── Column aliases → canonical field name ────────────────────────────────────
COL_MAP = {
    # Name
    "name":             "name",
    "spell name":       "name",
    "spell":            "name",
    # Level
    "level":            "level",
    "spell level":      "level",
    "lvl":              "level",
    # School
    "school":           "school",
    "school of magic":  "school",
    # Source
    "source":           "source",
    "book":             "source",
    "sourcebook":       "source",
    # Casting time
    "casting time":     "casting_time",
    "casting_time":     "casting_time",
    # Range
    "range":            "range",
    "spell range":      "range",
    # Components
    "components":       "components",
    "component":        "components",
    # Duration
    "duration":         "duration",
    # Concentration
    "concentration":    "concentration",
    "conc":             "concentration",
    "conc.":            "concentration",
    # Ritual
    "ritual":           "ritual",
    # Save type
    "save type":        "save_type",
    "save":             "save_type",
    "saving throw":     "save_type",
    # Classes / restrictions
    "classes":          "classes",
    "class":            "classes",
    "classrestrict":    "classes",
    "class restrict":   "classes",
    "available to":     "classes",
    # Description
    "description":      "description",
    "desc":             "description",
    "effect":           "description",
    "notes":            "description",
    # Character-specific
    "spellbook":        "_spellbook",
    "discovered":       "_discovered",
    "prepare":          "_prepare",
    "prepared":         "_prepare",
}


def normalize(h: str) -> str:
    return h.strip().lower()


def parse_bool(val) -> bool:
    return str(val).strip().lower() in ("yes", "true", "1", "x", "y")


def parse_level(val) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def parse_classes(val: str) -> list:
    if not val:
        return []
    return [c.strip() for c in val.replace(";", ",").split(",") if c.strip()]


def build_header_map(fieldnames: list) -> dict:
    """
    Map each CSV header to a canonical name.
    Handles duplicate headers — second occurrence of same canonical name is skipped.
    """
    result   = {}   # csv_header → canonical
    seen     = set()
    dupes    = []
    for h in fieldnames:
        canonical = COL_MAP.get(normalize(h))
        if canonical is None:
            continue
        if canonical in seen:
            dupes.append(h)
            continue
        result[h] = canonical
        seen.add(canonical)
    if dupes:
        print(f"  Note: duplicate/ignored columns: {dupes}")
    return result


def show_columns(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
    print(f"\nColumns in '{path}':")
    print(f"  {'CSV header':<25}  {'Maps to'}")
    print(f"  {'-'*25}  {'-'*25}")
    seen_canonical = set()
    for h in headers:
        canonical = COL_MAP.get(normalize(h))
        if canonical and canonical in seen_canonical:
            print(f"  {h:<25}  (duplicate — skipped)")
        elif canonical:
            print(f"  {h:<25}  {canonical}")
            seen_canonical.add(canonical)
        else:
            print(f"  {h:<25}  (not recognized — ignored)")


def seed_from_csv(path: str, default_source: str,
                  char_name: str = "", campaign_id: int = 0):

    before = count_spells_reference()
    ref_ok = 0
    book_ok = 0
    skipped = 0
    errors  = []

    do_char = bool(char_name and campaign_id)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader     = csv.DictReader(f)
        header_map = build_header_map(reader.fieldnames or [])

        if "name" not in header_map.values():
            print("ERROR: No 'Name' column recognized. Run --show-columns to inspect.")
            sys.exit(1)

        for raw_row in reader:
            # Re-key using canonical names
            row = {}
            for csv_col, canonical in header_map.items():
                row[canonical] = raw_row.get(csv_col, "").strip()

            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue

            # ── Reference upsert ────────────────────────────────────────────
            spell = {
                "name":          name,
                "level":         parse_level(row.get("level", 0)),
                "school":        row.get("school", ""),
                "casting_time":  row.get("casting_time", ""),
                "range":         row.get("range", ""),
                "components":    row.get("components", ""),
                "duration":      row.get("duration", ""),
                "concentration": parse_bool(row.get("concentration", "")),
                "ritual":        parse_bool(row.get("ritual", "")),
                "save_type":     row.get("save_type", ""),
                "classes":       parse_classes(row.get("classes", "")),
                "source":        row.get("source", "").strip() or default_source,
                "description":   row.get("description", ""),
            }
            try:
                upsert_spell_reference(spell)
                ref_ok += 1
            except Exception as e:
                errors.append((name, f"reference: {e}"))
                continue

            # ── Character spellbook ─────────────────────────────────────────
            if do_char:
                spellbook_flag = row.get("_spellbook", "")
                discovered     = parse_bool(row.get("_discovered", ""))
                prepared       = parse_bool(row.get("_prepare", ""))

                # Only add to spellbook if Spellbook col is truthy, or Discovered is true
                if parse_bool(spellbook_flag) or discovered:
                    # Look up spell id
                    matches = search_spells_reference(query=name, enabled_only=False, limit=1)
                    if matches:
                        spell_id = matches[0]["id"]
                        try:
                            add_to_spellbook(campaign_id, char_name, spell_id, prepared)
                            book_ok += 1
                        except Exception as e:
                            errors.append((name, f"spellbook: {e}"))

    after = count_spells_reference()
    new   = after - before
    print(f"\nReference: {ref_ok} rows processed, {new} new spells added to reference table.")
    if do_char:
        print(f"Spellbook:  {book_ok} spells added to {char_name}'s spellbook.")
    if skipped:
        print(f"Skipped:    {skipped} rows (no name).")
    if errors:
        print(f"Errors ({len(errors)}):")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"Total spells in reference table: {after}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import spells from CSV into spells_reference (and optionally a character's spellbook)."
    )
    parser.add_argument("csv_file",          nargs="?",        help="Path to the CSV file.")
    parser.add_argument("--default-source",  default="PHB",    help="Source label when CSV row has no Source column (default: PHB).")
    parser.add_argument("--char-name",       default="",       help="Character name to populate spellbook for.")
    parser.add_argument("--campaign-id",     default=0, type=int, help="Campaign ID for the character's spellbook.")
    parser.add_argument("--show-columns",    action="store_true", help="Print column mapping and exit.")
    args = parser.parse_args()

    if not args.csv_file:
        parser.print_help()
        sys.exit(1)

    if args.show_columns:
        show_columns(args.csv_file)
        sys.exit(0)

    init_db()
    seed_from_csv(
        path=args.csv_file,
        default_source=args.default_source,
        char_name=args.char_name,
        campaign_id=args.campaign_id,
    )
