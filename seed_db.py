"""
seed_db.py
One-time migration: loads characters and game state from a sessions JSON file
into the SQLite database.

Run:  python seed_db.py sessions/MuleskullSynch.json
Optional second arg: campaign name (default = filename stem)
"""

import json
import os
import sys
from db_manager import (
    init_db, create_campaign, list_campaigns,
    upsert_character, append_chronicle, save_session, save_map,
)


def seed(session_path: str, campaign_name: str = ""):
    init_db()
    with open(session_path, encoding="utf-8") as f:
        data = json.load(f)

    gs = data.get("game_state", {})

    # Derive a session key from the filename
    basename = os.path.splitext(os.path.basename(session_path))[0]
    session_key = basename

    if not campaign_name:
        campaign_name = basename

    # Find or create campaign
    existing = {c["name"]: c["id"] for c in list_campaigns()}
    if campaign_name in existing:
        campaign_id = existing[campaign_name]
        print(f"Using existing campaign '{campaign_name}' (id={campaign_id}).")
    else:
        campaign_id = create_campaign(campaign_name, "Migrated from JSON")
        print(f"Created campaign '{campaign_name}' (id={campaign_id}).")

    # Characters
    chars = gs.get("characters", [])
    for c in chars:
        upsert_character(c, campaign_id)
    print(f"Seeded {len(chars)} characters.")

    # Sessions table — stores conversation history blob
    last_sync = data.get("chronicle", [{}])[-1].get("sync_id", "")
    save_session(
        session_key=session_key,
        campaign_id=campaign_id,
        turn=data.get("turn", 0),
        game_state=gs,
        history=data.get("history", []),
        name=campaign_name,
    )
    print(f"Seeded session '{session_key}' (turn {data.get('turn', 0)}).")

    # Chronicle
    chronicle = data.get("chronicle", [])
    for entry in chronicle:
        append_chronicle(
            session_key=session_key,
            campaign_id=campaign_id,
            sync_id=entry.get("sync_id", ""),
            game_date=entry.get("game_date", ""),
            player_text=entry.get("player", ""),
            dm_text=entry.get("dm", ""),
            user_raw="",
        )
    print(f"Seeded {len(chronicle)} chronicle entries.")

    # Migrate any existing maps/*.json files
    maps_dir = os.path.join(os.path.dirname(session_path), "..", "maps")
    maps_dir = os.path.normpath(maps_dir)
    if os.path.isdir(maps_dir):
        migrated = 0
        for fname in os.listdir(maps_dir):
            if not fname.endswith(".json"):
                continue
            map_name = fname[:-5]
            try:
                with open(os.path.join(maps_dir, fname), encoding="utf-8") as mf:
                    map_data = json.load(mf)
                save_map(map_name, map_data.get("description", ""), map_data, campaign_id)
                migrated += 1
            except Exception as e:
                print(f"  Warning: could not migrate {fname}: {e}")
        print(f"Migrated {migrated} map(s) from maps/ directory.")

    print("Done.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "sessions/MuleskullSynch.json"
    cname = sys.argv[2] if len(sys.argv) > 2 else ""
    seed(path, cname)
