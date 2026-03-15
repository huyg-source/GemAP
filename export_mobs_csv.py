"""
One-time utility: export mobs table from local DB to mobs_seed.csv
Run: python export_mobs_csv.py
"""
import csv
import os
import sqlite3

DB_PATH = os.environ.get(
    "DND_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dnd_game.db"),
)

COLUMNS = [
    "name", "description", "ac", "hp_formula", "hp_avg", "speed",
    "str", "dex", "con", "int", "wis", "cha",
    "challenge", "xp", "size", "mob_type", "alignment",
    "melee_mod", "ranged_mod",
    "attack1", "attack1_range", "attack1_dmg",
    "attack2", "attack2_range", "attack2_dmg",
    "attack3", "attack3_range", "attack3_dmg",
    "source", "notes", "languages",
]

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT * FROM mobs ORDER BY name").fetchall()
con.close()

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mobs_seed.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r[c] for c in COLUMNS})

print(f"Exported {len(rows)} mobs to {out}")
