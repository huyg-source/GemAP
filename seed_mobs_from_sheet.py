"""
Seed mobs DB table from the 'Monsters' tab in the GemDMD Google Sheet.

Column order (0-based index):
 0  Entity_id
 1  Entity_Name
 2  Description
 3  AC
 4  HP (formula, e.g. "3d8+6")
 5  Speed
 6  STR  7  DEX  8  CON  9  INT  10 WIS  11 CHA
 12 Challenge (CR)
 13 Exp
 14 Size
 15 Type
 16 Alignment
 17 Page
 18 Status
 19 Melee Weapon Attack Modifier
 20 Ranged Weapon
 21 Attack1 name
 22 Attack1 range
 23 Damage Type (attack1)
 24 Attack2 name
 25 Attack2 range
 26 Damage Type (attack2)
 27 Attack3 name
 28 Attack3 range
 29 Damage Type (attack3)

Run: python seed_mobs_from_sheet.py
"""

import sys
from sheets_manager import _open_sheet
from db_manager import init_db, upsert_mob, count_mobs, _hp_avg


def _si(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def _ss(v):
    return str(v).strip() if v is not None else ""


def seed():
    init_db()
    print("Reading Monsters tab from Google Sheet...")
    sheet = _open_sheet()
    ws = sheet.worksheet("Monsters")
    rows = ws.get_all_values()
    if not rows:
        print("No data found.")
        return

    headers = rows[0]
    data_rows = rows[1:]

    imported = 0
    skipped_no_name = 0

    for row in data_rows:
        # Pad row to 30 columns
        row = list(row) + [''] * 30
        name = _ss(row[1])
        if not name:
            skipped_no_name += 1
            continue

        ac_raw = _ss(row[3])
        hp_raw = _ss(row[4])
        hp_formula = hp_raw
        try:
            ac = int(ac_raw) if ac_raw else 0
        except ValueError:
            ac = 0

        mob = {
            "name":         name,
            "description":  _ss(row[2]),
            "ac":           ac,
            "hp_formula":   hp_formula,
            "hp_avg":       _hp_avg(hp_formula),
            "speed":        _ss(row[5]),
            "str":          _si(row[6],  10),
            "dex":          _si(row[7],  10),
            "con":          _si(row[8],  10),
            "int":          _si(row[9],  10),
            "wis":          _si(row[10], 10),
            "cha":          _si(row[11], 10),
            "challenge":    _ss(row[12]),
            "xp":           _si(row[13], 0),
            "size":         _ss(row[14]),
            "mob_type":     _ss(row[15]),
            "alignment":    _ss(row[16]),
            "melee_mod":    _ss(row[19]),
            "ranged_mod":   _ss(row[20]),
            "attack1":      _ss(row[21]),
            "attack1_range":_ss(row[22]),
            "attack1_dmg":  _ss(row[23]),
            "attack2":      _ss(row[24]),
            "attack2_range":_ss(row[25]),
            "attack2_dmg":  _ss(row[26]),
            "attack3":      _ss(row[27]),
            "attack3_range":_ss(row[28]),
            "attack3_dmg":  _ss(row[29]),
            "source":       "GemDMD Sheet",
            "notes":        _ss(row[18]),  # Status field used as notes
        }
        upsert_mob(mob)
        imported += 1
        if ac or hp_formula:
            print(f"  {name} — AC {ac}, HP {hp_formula} (avg {mob['hp_avg']}), CR {mob['challenge']}")
        else:
            print(f"  {name} (name only)")

    total = count_mobs()
    print(f"\nDone. Upserted {imported} mobs ({skipped_no_name} blank rows skipped).")
    print(f"Total mobs in DB: {total}")


if __name__ == "__main__":
    seed()
