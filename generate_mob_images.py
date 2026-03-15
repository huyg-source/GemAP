"""
generate_mob_images.py

Generates portrait images for every mob in the bestiary that doesn't
already have one, using Imagen via the Gemini API.

Images are saved to  mob_images/<slug>.png  and the image_path column
in the mobs table is updated.

Usage:
    python generate_mob_images.py                # all mobs missing an image
    python generate_mob_images.py --limit 20     # first 20 missing
    python generate_mob_images.py --name "Orc"  # single mob by name
    python generate_mob_images.py --overwrite    # re-generate even if image exists

Rate limiting: Imagen allows ~2 requests/sec on most tiers.
The script pauses DELAY_SEC between requests (default 1.5 s).
"""

import os
import re
import sys
import time
import argparse

from db_manager import init_db, _conn, set_mob_image
from gemini_chat import get_api_key
from google import genai
from google.genai import types

MOB_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "mob_images")
DELAY_SEC      = 1.5   # seconds between API calls
IMAGE_MODEL    = "imagen-4.0-generate-001"


def build_prompt(mob: dict) -> str:
    size      = (mob.get("size",        "") or "").strip()
    mob_type  = (mob.get("mob_type",    "") or "").strip()
    alignment = (mob.get("alignment",   "") or "").strip()
    desc      = (mob.get("description", "") or "").strip()
    name      = mob["name"]

    subject = " ".join(filter(None, [size, alignment, mob_type, name]))
    flavor  = desc[:150] if desc else ""

    return (
        f"Fantasy RPG creature portrait of a {subject}. "
        + (flavor + ". " if flavor else "")
        + "Painterly digital art, full creature visible, dramatic lighting, "
        + "high quality D&D 5e monster art, no text, no watermarks."
    )


def slug(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.lower())


def mobs_needing_images(name_filter: str | None, overwrite: bool) -> list[dict]:
    with _conn() as con:
        if name_filter:
            rows = con.execute(
                "SELECT * FROM mobs WHERE name=? COLLATE NOCASE", (name_filter,)
            ).fetchall()
        elif overwrite:
            rows = con.execute("SELECT * FROM mobs ORDER BY name").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM mobs WHERE image_path='' OR image_path IS NULL ORDER BY name"
            ).fetchall()
    return [dict(r) for r in rows]


def generate_image(client, mob: dict) -> bytes | None:
    prompt = build_prompt(mob)
    try:
        result = client.models.generate_images(
            model=IMAGE_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_low_and_above",
                person_generation="allow_adult",
            ),
        )
        return result.generated_images[0].image.image_bytes
    except Exception as e:
        print(f"    ERROR generating image: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate mob portrait images.")
    parser.add_argument("--name",      type=str,  default=None, help="Single mob name")
    parser.add_argument("--limit",     type=int,  default=0,    help="Max number to process (0 = all)")
    parser.add_argument("--overwrite", action="store_true",     help="Re-generate even if image already exists")
    parser.add_argument("--delay",     type=float, default=DELAY_SEC, help=f"Seconds between API calls (default {DELAY_SEC})")
    args = parser.parse_args()

    init_db()
    os.makedirs(MOB_IMAGES_DIR, exist_ok=True)

    mobs = mobs_needing_images(args.name, args.overwrite)
    if args.limit > 0:
        mobs = mobs[:args.limit]

    if not mobs:
        print("No mobs need images. Done.")
        return

    print(f"Processing {len(mobs)} mob(s)...")

    client  = genai.Client(api_key=get_api_key())
    success = 0
    skipped = 0
    failed  = 0

    for i, mob in enumerate(mobs, 1):
        name     = mob["name"]
        filename = f"{slug(name)}.png"
        filepath = os.path.join(MOB_IMAGES_DIR, filename)

        # Skip if file already exists on disk and we're not overwriting
        if not args.overwrite and os.path.exists(filepath):
            print(f"[{i}/{len(mobs)}] SKIP  {name}  (file exists, DB missing path — fixing)")
            set_mob_image(name, filename)
            skipped += 1
            continue

        print(f"[{i}/{len(mobs)}] Generating image for: {name}")

        img_bytes = generate_image(client, mob)
        if img_bytes is None:
            failed += 1
        else:
            with open(filepath, "wb") as fh:
                fh.write(img_bytes)
            set_mob_image(name, filename)
            print(f"    Saved: {filename}")
            success += 1

        # Rate-limit pause (skip after last item)
        if i < len(mobs):
            time.sleep(args.delay)

    print(f"\nDone. Success: {success}  Skipped: {skipped}  Failed: {failed}")


if __name__ == "__main__":
    main()
