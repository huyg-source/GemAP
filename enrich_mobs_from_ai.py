"""
enrich_mobs_from_ai.py

Fills in missing stat blocks for mobs in the DB using Gemini.
Only processes mobs where ac=0 AND hp_formula=''.
Batches 10 names per request to Gemini, which returns a JSON array.

Run:
    python enrich_mobs_from_ai.py               # all missing
    python enrich_mobs_from_ai.py --limit 50    # first 50 missing
    python enrich_mobs_from_ai.py --name "Orc"  # single mob by name

Stats already in the DB are never overwritten (upsert preserves existing data
via the CASE WHEN image_path guard, but all other fields ARE updated here because
we're intentionally filling them in).
"""

import sys
import json
import time
import argparse
from db_manager import init_db, _conn, upsert_mob, _hp_avg
from gemini_chat import get_api_key
from google import genai
from google.genai import types

BATCH_SIZE  = 10
DELAY_SEC   = 1.5   # pause between batches to stay within rate limits

SYSTEM_PROMPT = """You are a D&D 5e rules expert. For each monster name provided, return ONLY a valid JSON array
where each element is an object with EXACTLY these fields (no extras):

{
  "name":           "<exact name as given>",
  "description":    "<one or two sentence flavour/lore description>",
  "ac":             <integer armor class>,
  "hp_formula":     "<dice expression e.g. 3d8+6>",
  "speed":          "<e.g. 30 ft., fly 60 ft.>",
  "str": <int>, "dex": <int>, "con": <int>,
  "int": <int>, "wis": <int>, "cha": <int>,
  "challenge":      "<CR as string e.g. 0.25 or 1 or 17>",
  "xp":             <integer xp reward>,
  "size":           "<Tiny|Small|Medium|Large|Huge|Gargantuan>",
  "mob_type":       "<beast|undead|humanoid|fiend|dragon|construct|elemental|fey|giant|monstrosity|ooze|plant|celestial|aberration|other>",
  "alignment":      "<e.g. chaotic evil, neutral, unaligned>",
  "melee_mod":      "<melee attack bonus as string e.g. +4, or empty string>",
  "ranged_mod":     "<ranged attack bonus as string e.g. +3, or empty string>",
  "attack1":        "<primary attack name e.g. Claws, Bite, Longsword, or empty>",
  "attack1_range":  "<reach or range e.g. 5 ft., 80/320 ft., or empty>",
  "attack1_dmg":    "<damage expression + type e.g. 2d6+3 slashing, or empty>",
  "attack2":        "<second attack name or empty>",
  "attack2_range":  "<reach/range or empty>",
  "attack2_dmg":    "<damage or empty>",
  "attack3":        "<third attack name or empty>",
  "attack3_range":  "<reach/range or empty>",
  "attack3_dmg":    "<damage or empty>",
  "languages":      "<comma-separated languages or empty string>"
}

Use official D&D 5e Monster Manual / SRD stats. If a creature has no official stats
(e.g. it's only a name reference), use your best estimate based on creature type and lore.
Return ONLY the JSON array. No markdown, no explanation, no code fences."""


def _get_missing(limit=None, name=None):
    with _conn() as con:
        if name:
            rows = con.execute(
                "SELECT name FROM mobs WHERE name=? COLLATE NOCASE", (name,)
            ).fetchall()
        else:
            q = "SELECT name FROM mobs WHERE ac=0 AND hp_formula='' ORDER BY name"
            if limit:
                q += f" LIMIT {limit}"
            rows = con.execute(q).fetchall()
    return [r[0] for r in rows]


def _call_gemini(names: list[str]) -> list[dict]:
    client = genai.Client(api_key=get_api_key())
    prompt = "Fill in stats for these D&D 5e monsters:\n" + "\n".join(f"- {n}" for n in names)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _apply(mob_data: dict):
    """Upsert mob with AI-provided stats. Preserves existing image_path."""
    name = mob_data.get("name", "").strip()
    if not name:
        return
    # Carry forward existing image_path
    with _conn() as con:
        row = con.execute(
            "SELECT image_path, languages FROM mobs WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    existing_image = row["image_path"] if row else ""
    existing_langs = row["languages"] if row else ""

    hp_formula = str(mob_data.get("hp_formula", "") or "")
    mob_data["hp_avg"]      = _hp_avg(hp_formula)
    mob_data["image_path"]  = existing_image  # preserve
    # Don't overwrite manually set languages
    if existing_langs and not mob_data.get("languages"):
        mob_data["languages"] = existing_langs

    upsert_mob(mob_data)


def main():
    parser = argparse.ArgumentParser(description="Enrich mob stats via Gemini AI")
    parser.add_argument("--limit", type=int, default=None, help="Max mobs to process")
    parser.add_argument("--name",  type=str, default=None, help="Single mob name to enrich")
    args = parser.parse_args()

    init_db()
    names = _get_missing(limit=args.limit, name=args.name)

    if not names:
        print("No mobs with missing stats found.")
        return

    print(f"Enriching {len(names)} mob(s) in batches of {BATCH_SIZE}...\n")
    total_done = 0
    total_failed = 0

    for i in range(0, len(names), BATCH_SIZE):
        batch = names[i:i + BATCH_SIZE]
        print(f"Batch {i//BATCH_SIZE + 1}: {', '.join(batch)}")
        try:
            results = _call_gemini(batch)
            # Match results back to batch names (AI may reorder)
            result_map = {r.get("name", "").strip().lower(): r for r in results if isinstance(r, dict)}
            for name in batch:
                mob_data = result_map.get(name.lower())
                if mob_data:
                    mob_data["name"] = name  # ensure exact original casing
                    _apply(mob_data)
                    hp = mob_data.get('hp_formula','?')
                    ac = mob_data.get('ac','?')
                    cr = mob_data.get('challenge','?')
                    print(f"  [OK] {name} - AC {ac}, HP {hp}, CR {cr}")
                    total_done += 1
                else:
                    print(f"  [--] {name} - not in AI response")
                    total_failed += 1
        except Exception as e:
            print(f"  ERROR on batch: {e}")
            total_failed += len(batch)

        if i + BATCH_SIZE < len(names):
            time.sleep(DELAY_SEC)

    print(f"\nDone. {total_done} enriched, {total_failed} failed.")


if __name__ == "__main__":
    main()
