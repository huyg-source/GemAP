"""
D&D DM Web App
Browser-based DM session with party tracking and chronicle.
Run: python dm_web.py
"""

import eventlet
eventlet.monkey_patch()

import os
import json
import re
import uuid
import signal
import logging
import logging.handlers
import threading
import subprocess
import functools
import io
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()   # load .env before anything reads env vars

from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, session as flask_session,
                   redirect, url_for)
from flask_socketio import SocketIO, emit, join_room, leave_room
from google import genai
from google.genai import types
from gemini_chat import get_api_key

# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt       = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt   = "%Y-%m-%d %H:%M:%S"
    handlers  = [logging.StreamHandler()]   # always log to stdout (Render captures it)

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    handlers.append(logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,   # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    ))

    logging.basicConfig(level=log_level, format=fmt, datefmt=datefmt, handlers=handlers)
    # Quieten noisy third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("engineio").setLevel(logging.WARNING)
    logging.getLogger("socketio").setLevel(logging.WARNING)

_setup_logging()
log = logging.getLogger("dnd")
from db_manager import (
    init_db,
    create_campaign, list_campaigns, get_campaign,
    update_from_session, append_session_entry, read_main_tab_characters,
    save_session as db_save_session,
    load_session as db_load_session,
    list_sessions as db_list_sessions,
    read_chronicle as db_read_chronicle,
    append_chronicle, append_story,
    upsert_character, read_all_characters,
    upsert_magic_item, search_magic_items, get_magic_item, count_magic_items,
    search_mundane_items, count_mundane_items,
    upsert_spell_reference, search_spells_reference, get_spell_reference,
    get_spell_with_override, delete_spell_reference, get_spellbook, add_to_spellbook,
    get_spell_override, set_spell_override, clear_spell_override,
    remove_from_spellbook, set_spell_prepared, update_spellbook_notes, seed_spellbook_from_names,
    count_spells_reference, list_spell_sources, set_source_enabled,
    get_calendar_day, get_calendar_month, get_calendar_full, advance_date,
    upsert_npc, get_npc, get_npc_by_name, list_npcs, set_npc_attitude, delete_npc,
    get_npcs_at_location,
    get_npc_affinity, get_all_npc_affinities, set_npc_affinity, adjust_npc_affinity,
    seed_world_factions,
    create_org, get_org, list_orgs, update_org, delete_org,
    add_org_member, remove_org_member, get_org_members, get_entity_orgs,
    get_org_affinity, get_all_org_affinities, set_org_affinity, adjust_org_affinity,
    compute_interaction_org_score,
    add_npc_offer, get_offer, list_npc_offers, list_all_active_offers,
    set_offer_status, delete_offer,
    set_character_portrait, delete_character,
    upsert_mob, search_mobs, get_mob, get_mob_with_override, count_mobs, delete_mob,
    set_mob_image, update_mob_languages,
    get_mob_override, set_mob_override, clear_mob_override,
    get_mob_knowledge, set_mob_knowledge, advance_mob_knowledge,
    list_mobs_for_manual, KNOWLEDGE_RANKS,
    create_player, get_player, touch_player,
    create_player_token, get_player_token, list_player_tokens,
    update_player_token, touch_player_token, deactivate_player_token,
    save_round_submission, get_round_submissions, clear_round_submissions,
    save_player_message, get_player_messages, get_all_player_messages,
    mark_messages_read,
    log_api_call, get_usage_by_session, get_usage_by_type, get_usage_totals,
    get_user_campaign_count, get_user_character_count,
)

try:
    import requests as http_req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

app = Flask(__name__)
_secret = os.environ.get("DND_SECRET_KEY", "")
if not _secret:
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError("DND_SECRET_KEY environment variable must be set in production.")
    _secret = "dnd-dev-secret-local-only"
app.secret_key = _secret
_cors_origins = os.environ.get("DND_ALLOWED_ORIGINS", "*")
if _cors_origins != "*":
    _cors_origins = [o.strip() for o in _cors_origins.split(",")]
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins=_cors_origins)

# ── Flask-Login ────────────────────────────────────────────────────────────────
from auth import auth_bp, login_manager, is_pro
from flask_login import current_user
from stripe_routes import stripe_bp

login_manager.init_app(app)
app.register_blueprint(auth_bp)
app.register_blueprint(stripe_bp)

# GM password — set env var DND_GM_PASSWORD to override default
GM_PASSWORD = os.environ.get("DND_GM_PASSWORD", "dungeonmaster")

_DATA_DIR      = os.environ.get("DND_DATA_DIR", os.path.dirname(__file__))
SESSIONS_DIR   = os.path.join(_DATA_DIR, "sessions")
PORTRAITS_DIR  = os.path.join(_DATA_DIR, "portraits")
MOB_IMAGES_DIR = os.path.join(_DATA_DIR, "mob_images")
os.makedirs(SESSIONS_DIR,   exist_ok=True)
os.makedirs(PORTRAITS_DIR,  exist_ok=True)
os.makedirs(MOB_IMAGES_DIR, exist_ok=True)

PORT = 5001
URL  = f"http://localhost:{PORT}/dm/"


# ── Auth helpers ────────────────────────────────────────────────────────────────

def gm_required(f):
    """Decorator: allow GM password session OR a logged-in pro user account."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if flask_session.get("gm_logged_in"):
            return f(*args, **kwargs)
        if current_user.is_authenticated:
            if current_user.is_pro():
                return f(*args, **kwargs)
            return redirect(url_for("stripe_bp.checkout"))
        return redirect(url_for("gm_login"))
    return decorated


def _log_usage(call_type: str, response, model: str = ""):
    """Extract token counts from a Gemini response and write to usage log."""
    try:
        usage = response.usage_metadata
        uid   = current_user.id if current_user.is_authenticated else None
        log_api_call(
            session_key   = state.get("session_key", ""),
            campaign_id   = state.get("campaign_id") or 0,
            call_type     = call_type,
            model         = model or state.get("model", ""),
            prompt_tokens = getattr(usage, "prompt_token_count",     0) or 0,
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0,
            user_id       = uid,
        )
    except Exception:
        pass


def _gm_room():
    """SocketIO room name for GM-only events in the current session."""
    return f"gm_{state.get('session_key', 'nosession')}"


def _session_room():
    """SocketIO room for all participants in the current session."""
    return f"session_{state.get('session_key', 'nosession')}"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None

def open_in_chrome():
    chrome = find_chrome()
    if chrome:
        subprocess.Popen([chrome, "--new-window", URL])
    else:
        import webbrowser
        webbrowser.open(URL)


# ── System instruction ─────────────────────────────────────────────────────────

BASE_SYSTEM = """
You are a Dungeon Master for Dungeons & Dragons 5th Edition (D&D 5e).
Follow the official D&D 5e rules for all rulings, combat, and mechanics.

RESPONSE FORMAT RULES — absolute, never broken:
- Respond with a single valid JSON object and nothing else.
- No markdown, code fences, backticks, or prose outside the JSON.
- No trailing commas. No comments inside JSON.
- "buffs" and "debuffs" must always be JSON arrays — [] if empty.
- "gold" and "xp" must always be integers — 0 if unknown.
- "hp", "max_hp", "ac", and "level" must always be integers — 0 if unknown.

STATE PERSISTENCE RULES:
- Carry all values forward unless the current turn changes them.
- Repeat last known HP, gold, xp, location, buffs, debuffs if unchanged.
- Only include characters that have been introduced.

SYNC ID RULES:
- User message begins with [sync_id: XXXX]. Copy it exactly into "sync_id".

JSON STRUCTURE:
{
  "sync_id": "<copied from user message>",
  "game_date": "<in-world date>",
  "session_mode": "<combat|roleplay|narrative — set to 'combat' when violence breaks out or initiative is called, 'roleplay' during NPC social encounters, 'narrative' for exploration/travel/story>",
  "player_restatement": "<player input as clean third-person narrative prose>",
  "dm_response": "<full DM narrative response>",
  "game_state": {
    "gold": <integer>,
    "xp":   <integer>,
    "location": "<current location>",
    "characters": [
      {
        "name":    "<name>",
        "class":   "<class>",
        "level":   <integer>,
        "hp":      <integer>,
        "max_hp":  <integer>,
        "ac":      <integer>,
        "buffs":   [],
        "debuffs": []
      }
    ]
  },
  "npc_updates": [
    {
      "name":           "<NPC name>",
      "npc_type":       "<store_owner|employee|mercenary|craftsman|bureaucrat|innkeeper|guard|noble|criminal|other or empty>",
      "attitude_delta": <integer -30 to +30, 0 if unchanged>,
      "location":       "<location if known, else empty string>",
      "notes":          "<brief note about this interaction, else empty string>",
      "new_offers": [
        {
          "offer_type":  "item or quest",
          "title":       "<item name or quest title>",
          "description": "<detail>",
          "price_gp":    <integer for items, null for quests>,
          "expires_date":"<in-world date or empty>"
        }
      ]
    }
  ],
  "combat_updates": [
    {
      "name":   "<exact combatant name as shown in initiative order>",
      "hp":     <new current HP as integer, or -1 if unchanged>,
      "status": "<none|incapacitated|dead — set incapacitated or dead when the combatant drops to 0 HP, is knocked out, dies, or is otherwise unable to act>",
      "grid_x": <integer grid column 0-based, or -1 if not moving>,
      "grid_y": <integer grid row 0-based, or -1 if not moving>
    }
  ],
  "map_layout": {
    "room_type":        "<chamber|corridor|cave|hall|crypt|courtyard|tavern|sewer|throne_room|city_street|graveyard|forest_road|mountain_pass_road|meadow|dense_forest>",
    "shape":            "<rectangle|L|T|U|cross>",
    "width_ft":         <integer multiple of 5, e.g. 30>,
    "height_ft":        <integer multiple of 5, e.g. 20>,
    "features":         ["<zero or more from: pillars, altar, throne, pit, tables, crates, chest, stairs, barricade, barricade_ew, door_north, door_south, door_east, door_west>"],
    "feature_positions": {
      "<feature_name>": {"x_pct": <0.0–1.0 fraction of room width>, "y_pct": <0.0–1.0 fraction of room height>}
    },
    "entrances": [
      {"side": "<north|south|east|west>", "offset_pct": <0.0–1.0 position along that wall>}
    ],
    "token_starts": {
      "<combatant name>": {"x_pct": <0.0–1.0>, "y_pct": <0.0–1.0>}
    },
    "scene_description": "<one evocative sentence describing the space — shown to players>"
  },
  "loot_awards": [
    {
      "name":     "<item name>",
      "qty":      <integer, default 1>,
      "value_gp": <integer estimated value in gold pieces, 0 if unknown>,
      "notes":    "<brief description or source, e.g. 'found on goblin chieftain'>"
    }
  ],
  "rp_notes_updates": [
    {
      "name": "<exact character name>",
      "note": "<one sentence observation about revealed personality, behavior, or character development>"
    }
  ],
  "faction_mentions": [
    {
      "name":        "<exact faction or organization name>",
      "org_type":    "<party|adventurers|guild|military|religious|criminal|noble_house|merchant_league|secret_society|government|other>",
      "description": "<one sentence description of this faction>",
      "headquarters":"<city or region, or empty>",
      "npc_members": ["<NPC name if they were revealed as a member this turn>"]
    }
  ]
}

FACTION MENTION RULES:
- Include any named faction or organization that is meaningfully referenced for the FIRST TIME this session.
- Do NOT re-include factions already well established in the campaign context.
- Include factions the party encounters, hears about, or discovers NPC allegiances to.
- npc_members: only list NPCs from this turn who were revealed as members or agents of this faction.
- omit "faction_mentions" entirely (or use []) if no new factions appear this turn.

NPC UPDATE RULES:
- Only include NPCs that were meaningfully interacted with this turn.
- attitude_delta: positive = warmer, negative = colder. Keep changes proportional (-5 to +5 for minor, up to ±20 for major events).
- new_offers: only add when the NPC explicitly offers something new. Leave as [] otherwise.
- omit "npc_updates" entirely (or use []) if no NPCs were involved this turn.

COMBAT UPDATE RULES:
- Populate "combat_updates" on every combat turn for any combatant whose HP, status, or position changed.
- "hp": set to the new integer HP value whenever HP changes (damage taken, healing received). Use -1 if HP did not change.
- "status": set to "incapacitated" when a combatant reaches 0 HP or is knocked unconscious; "dead" if killed outright; "none" if currently conscious and able to act.
- Always report "incapacitated" or "dead" the turn it happens — do not wait for subsequent turns.
- "grid_x" / "grid_y": set to the combatant's new grid position (0-based column/row) whenever they move. The battle map uses 5-ft squares; use the most recent map_layout dimensions to calculate — e.g. a 30×20 ft room is 6 columns × 4 rows. Origin (0,0) is top-left. Use -1 for both if the combatant did not move this turn.
- Include EVERY combatant that moved this turn — this includes player characters (PCs) as well as enemies. When a player describes their character moving, you MUST include that PC in combat_updates with their new grid_x/grid_y.
- PC starting positions: party members default to the left side of the map (gx≈2) and enemies to the right (gx≈8). When a PC moves toward enemies, increase their gx. When enemies close in, decrease their gx.
- omit "combat_updates" entirely (or use []) outside of combat.

MAP LAYOUT RULES:
- Include "map_layout" ONLY when the party enters a new area, combat begins in a new location, or the scene explicitly moves to a different space. Omit it on all subsequent turns in the same location.
- "room_type": pick the best match —
    INDOOR: chamber (default stone room), corridor (narrow passage), cave (irregular stone), hall (large open), crypt (burial alcoves), courtyard (open courtyard), tavern (common room), sewer (underground channel), throne_room (grand with dais).
    OUTDOOR: city_street (cobblestone road between buildings), graveyard (burial ground with headstones), forest_road (dirt path through trees), mountain_pass_road (rocky mountain pass), meadow (open grassy field), dense_forest (heavy forest with many trees).
- "shape": the floor plan shape. Use "rectangle" for plain rooms; "L" for an L-shaped space (e.g. a room with an alcove wing); "T" for a T-junction or room with a central corridor; "U" for a U-shaped chamber with a central open pit or courtyard; "cross" for a crossroads or four-way intersection. Default "rectangle" when in doubt.
- "width_ft" and "height_ft": the bounding box dimensions in feet, always multiples of 5. Typical ranges: corridor 10×30, chamber 20×20, hall 40×30, tavern 30×25, city_street 20×50, forest_road 20×40, meadow 50×50, graveyard 40×40.
- "features": include only elements clearly present or strongly implied in the narrative. Options: pillars (stone columns), altar (ritual stone slab), throne (ornate seat), pit (open floor pit), tables (furniture), crates (stacked boxes/barrels), chest (treasure chest), stairs (staircase), barricade (vertical wall across room with gap), barricade_ew (horizontal wall across room with gap), door_north/south/east/west (exit door on that wall).
- "feature_positions": for each named feature (matching an entry in "features"), provide its approximate position as a fraction of the room's width (x_pct) and height (y_pct), where 0.0 is the left/top edge and 1.0 is the right/bottom edge. Example: altar at room centre = {"altar": {"x_pct": 0.5, "y_pct": 0.5}}. Omit features that should be randomly scattered (e.g. crates, pillars).
- "entrances": list of doorways or passages leading out of this space. Each has a "side" (north/south/east/west) and an "offset_pct" (0.0–1.0 position along that wall, 0.5 = centre). Include at least one entrance unless it is a dead-end pocket.
- "token_starts": for each combatant who should begin at a specific narrative position, provide x_pct/y_pct. Example: a boss enthroned at the far end = {"Boss": {"x_pct": 0.85, "y_pct": 0.5}}. Party members who enter from a doorway should be near that entrance. Omit combatants whose position doesn't matter — they will be placed automatically.
- "scene_description": one evocative sentence (15–25 words) describing the space as the players would perceive it. This is shown directly to players on their map view.
- Outdoor room types (city_street, graveyard, forest_road, mountain_pass_road, meadow, dense_forest) auto-generate appropriate terrain obstacles — you do not need to list trees, headstones, or boulders in features.
- Omit "map_layout" entirely if the location has not changed since the last turn.

AC CALCULATION RULES:
- Always compute and return the correct AC for every character in game_state.characters each turn.
- The party context shows each character's equipped items with slot labels (e.g. "Chain Mail [armor]", "Shield [off_hand]").
- Calculate AC from the armor slot using standard D&D 5e values:
    No armor:        10 + DEX mod
    Padded:          11 + DEX mod
    Leather:         11 + DEX mod
    Studded Leather: 12 + DEX mod
    Hide:            12 + DEX mod (max +2 DEX)
    Chain Shirt:     13 + DEX mod (max +2 DEX)
    Scale Mail:      14 + DEX mod (max +2 DEX)
    Breastplate:     14 + DEX mod (max +2 DEX)
    Half Plate:      15 + DEX mod (max +2 DEX)
    Ring Mail:       14 (no DEX bonus)
    Chain Mail:      16 (no DEX bonus)
    Splint:          17 (no DEX bonus)
    Plate:           18 (no DEX bonus)
- Add +2 AC if a shield is equipped in the off_hand slot.
- Special class features: Barbarian Unarmored Defense = 10 + DEX mod + CON mod (if no armor); Monk Unarmored Defense = 10 + DEX mod + WIS mod (if no armor or shield); Mage Armor = 13 + DEX mod.
- If the item name in the armor slot contains "AC <number>" (e.g. "Elven Chain AC 16"), use that number as the base before adding any applicable DEX bonus.
- Recalculate and update "ac" in game_state.characters whenever equipment changes are described or at the start of each session.

LOOT AWARD RULES:
- Populate "loot_awards" when the party finds treasure, loots a body, opens a chest, receives a reward, or gains any tangible item during the narrative.
- Include each item as a separate entry with an accurate D&D 5e market value in "value_gp". Use 0 if the value is unknown or the item is non-standard.
- "qty": number of identical items (e.g. 3 health potions = qty 3, not 3 entries).
- "notes": brief source ("looted from orc warchief", "found in trapped chest", "reward from Mayor").
- Gold coins awarded as part of loot: include as a single entry with name "Gold Pieces" and value_gp equal to the amount.
- Omit "loot_awards" entirely (or use []) if no items were found or awarded this turn.

RP NOTES UPDATE RULES:
- Use "rp_notes_updates" to record meaningful observations about a character's personality, behavior, or development that emerged during this turn.
- Only use when something genuinely new or notable is revealed — a surprising reaction, a relationship moment, a value being tested, a habit becoming clear.
- One entry per character, one sentence per entry. Be specific and behavioral, not generic ("refused to leave a wounded stranger despite the danger" not "is heroic").
- Do NOT add entries for things already documented in the character's existing RP notes.
- Omit "rp_notes_updates" entirely (or use []) if nothing notable emerged this turn. Use sparingly — quality over quantity.
"""

COMBAT_MODE_INSTRUCTIONS = """
CURRENT MODE: COMBAT (Turn-Based D&D 5e)
- Combat is in progress. Enforce strict D&D 5e turn-based rules.
- A COMBAT CONTEXT block will appear at the start of the user message showing the initiative order,
  the current round number, and which character has the ACTIVE TURN.
- If the active character is marked NPC or Mob, you choose and narrate their action — do not wait for player input.
- PC turns: the player will describe what they do; you adjudicate using D&D 5e rules.
- Enforce action economy each turn: one Action, one Bonus Action, Movement (up to speed), one free object interaction.
  Reactions may trigger on other characters' turns.
- Resolve attacks (roll to hit vs target AC), damage, saving throws, and conditions per RAW.
- After resolving the turn, briefly note who is up next.
- Keep responses focused and mechanical while maintaining narrative tension.
"""

ROLEPLAY_MODE_INSTRUCTIONS = """
CURRENT MODE: ROLEPLAY (Social Encounter)
- A social encounter or NPC interaction is in progress. No combat turn order is in effect.
- Voice all NPCs with distinct personality, motivation, accent, and agenda.
- Apply D&D 5e social mechanics when dramatically appropriate:
  Persuasion (CHA), Deception (CHA), Intimidation (CHA or STR), Insight (WIS).
- Track NPC attitude (hostile → unfriendly → indifferent → friendly → helpful) and shift it based on PC actions.
- Multiple party members may engage simultaneously; no strict turn structure is required.
- Prioritise rich, character-driven dialogue over mechanical summaries.
"""

NARRATIVE_MODE_INSTRUCTIONS = """
CURRENT MODE: NARRATIVE (Free Exploration / Story)
- The party is in free exploration, travel, downtime, or story progression.
- Describe scenes richly: sights, sounds, smells, atmosphere, and world-building details.
- Handle skill checks, hazards, traps, and random encounters as appropriate to D&D 5e rules.
- No turn structure; respond naturally to the party's collective actions.
- Drive the story forward with hooks, tension, consequences, and memorable moments.
"""

_MODE_INSTRUCTIONS = {
    "combat":    COMBAT_MODE_INSTRUCTIONS,
    "roleplay":  ROLEPLAY_MODE_INSTRUCTIONS,
    "narrative": NARRATIVE_MODE_INSTRUCTIONS,
}

def build_system(party_context: str = "", session_mode: str = "narrative",
                 combat_context: str = "", location_npcs: list = None) -> str:
    system = BASE_SYSTEM + _MODE_INSTRUCTIONS.get(session_mode, NARRATIVE_MODE_INSTRUCTIONS)
    if combat_context:
        system += f"\n\nCOMBAT CONTEXT:\n{combat_context}"
    if location_npcs:
        lines = []
        for n in location_npcs:
            attitude_label = (
                "hostile" if n["attitude"] <= -61 else
                "unfriendly" if n["attitude"] <= -21 else
                "indifferent" if n["attitude"] <= 20 else
                "friendly" if n["attitude"] <= 60 else "helpful"
            )
            line = f"- {n['name']} [{n.get('npc_type','') or 'NPC'}] attitude={n['attitude']} ({attitude_label})"
            if n.get("notes"):
                line += f": {n['notes']}"
            lines.append(line)
        system += "\n\nNPCS AT CURRENT LOCATION (roleplay these characters):\n" + "\n".join(lines)
    if party_context:
        system += f"\n\nPARTY CONTEXT (from D&D Beyond):\n{party_context}"
    return system


# ── Per-campaign session state ─────────────────────────────────────────────────
#
# `state` and `round_state` are proxy objects.  Every attribute access is
# automatically routed to the dict for the *current campaign*, identified by:
#   1. _thread_cid.id   — set explicitly by background threads & socket handlers
#   2. flask_session["gm_campaign_id"] or ["player_campaign"] — set by before_request
#
# This allows multiple GM browser sessions (different campaigns) to coexist
# in the same Flask process without sharing state.

_states_store: dict = {}          # campaign_id -> state dict
_rs_store:     dict = {}          # campaign_id -> round_state dict
_states_lock        = threading.Lock()
_thread_cid         = threading.local()   # per-thread active campaign id


def _make_default_state() -> dict:
    return {
        "history":                [],
        "turn":                   0,
        "session_key":            None,
        "campaign_id":            None,
        "campaign_name":          "",
        "model":                  "gemini-2.5-flash",
        "party_context":          "",
        "combat_active":          False,
        "session_mode":           "narrative",
        "combat_ui_state":        {},
        "party_loot":             [],
        "game_state": {
            "gold": 0, "xp": 0, "game_date": "", "location": "", "characters": []
        },
        "chronicle":              [],
        "pending_player_actions": [],
        "party_chat":             [],
    }


def _make_default_round_state() -> dict:
    return {"open": False, "round_num": 0}


def _active_cid() -> int:
    """Return the campaign_id for the current thread/request context."""
    tid = getattr(_thread_cid, 'id', None)
    if tid is not None:
        return int(tid)
    try:
        cid = flask_session.get("gm_campaign_id") or flask_session.get("player_campaign")
        return int(cid) if cid else 0
    except RuntimeError:
        return 0   # outside any request context


def _get_campaign_state(cid: int) -> dict:
    with _states_lock:
        if cid not in _states_store:
            _states_store[cid] = _make_default_state()
        _state_accessed[cid] = datetime.now().timestamp()
        return _states_store[cid]


def _get_round_state_dict(cid: int) -> dict:
    with _states_lock:
        if cid not in _rs_store:
            _rs_store[cid] = _make_default_round_state()
        return _rs_store[cid]


class _StateProxy:
    """Dict-like proxy that routes to the per-campaign state for the current request/thread."""
    def _d(self):                    return _get_campaign_state(_active_cid())
    def __getitem__(self, k):        return self._d()[k]
    def __setitem__(self, k, v):     self._d()[k] = v
    def __delitem__(self, k):        del self._d()[k]
    def __contains__(self, k):       return k in self._d()
    def __iter__(self):              return iter(self._d())
    def __repr__(self):              return repr(self._d())
    def get(self, k, d=None):        return self._d().get(k, d)
    def update(self, *a, **kw):      self._d().update(*a, **kw)
    def pop(self, k, *a):            return self._d().pop(k, *a)
    def keys(self):                  return self._d().keys()
    def values(self):                return self._d().values()
    def items(self):                 return self._d().items()
    def clear(self):                 self._d().clear()
    def setdefault(self, k, d=None): return self._d().setdefault(k, d)


class _RoundStateProxy:
    """Dict-like proxy routing to the per-campaign round state."""
    def _d(self):                return _get_round_state_dict(_active_cid())
    def __getitem__(self, k):    return self._d()[k]
    def __setitem__(self, k, v): self._d()[k] = v
    def __contains__(self, k):   return k in self._d()
    def __repr__(self):          return repr(self._d())
    def get(self, k, d=None):    return self._d().get(k, d)
    def update(self, *a, **kw):  self._d().update(*a, **kw)


state       = _StateProxy()
round_state = _RoundStateProxy()

PARTY_CHAT_MAX  = 50
_STATE_TTL_SECS = 4 * 60 * 60   # evict campaign state after 4 hours of inactivity
_state_accessed: dict = {}       # campaign_id -> last access timestamp


def _touch_state(cid: int):
    """Record that a campaign state was just accessed."""
    _state_accessed[cid] = datetime.now().timestamp()


def _evict_stale_states():
    """Background thread: remove campaign states idle longer than TTL."""
    while True:
        threading.Event().wait(timeout=15 * 60)   # check every 15 minutes
        cutoff = datetime.now().timestamp() - _STATE_TTL_SECS
        with _states_lock:
            stale = [cid for cid, ts in _state_accessed.items() if ts < cutoff]
            for cid in stale:
                _states_store.pop(cid, None)
                _rs_store.pop(cid, None)
                _state_accessed.pop(cid, None)
                log.info("Evicted idle campaign state: campaign_id=%s", cid)


def _new_session_key() -> str:
    return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _history_to_json() -> list:
    return [
        {"role": c.role, "parts": [{"text": p.text} for p in c.parts]}
        for c in state["history"]
    ]

STORY_SYSTEM = """You are a creative fantasy author writing a D&D campaign as a novel.
You will receive a single game turn: what the players did and the DM's narrative response.
Write one flowing prose paragraph (150-250 words) in the style of a well-crafted fantasy novel.
Rules:
- Past tense, third person.
- Focus on atmosphere, character actions, tension, and consequences.
- No game mechanics, dice rolls, HP numbers, or stat references.
- No headings, labels, or meta-commentary — pure narrative prose only.
"""


def _write_story_entry(session_key: str, campaign_id: int, sync_id: str,
                        game_date: str, player_text: str, dm_text: str,
                        location: str, model: str = "gemini-2.5-flash"):
    """Called in a background thread — generates and saves a narrative paragraph."""
    prompt = (
        f"Location: {location}\n"
        f"What the players did: {player_text}\n"
        f"What happened: {dm_text}"
    )
    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(system_instruction=STORY_SYSTEM),
        )
        append_story(session_key, campaign_id, sync_id, game_date, response.text.strip())
    except Exception as e:
        log.error("Story generation failed for %s: %s", sync_id, e)


def generate_sync_id(turn: int) -> str:
    return f"TURN-{turn:03d}-{datetime.now().strftime('%Y%m%d-%H%M')}"


def parse_dm_response(raw: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _merge_ai_characters(ai_chars: list, current_chars: list) -> list:
    """Merge AI-returned character updates into the current characters list.
    The AI only returns a small subset of fields (hp, max_hp, ac, buffs, debuffs, class, level).
    We update those fields in place and preserve everything else (items, spells, race, stats, etc.).
    """
    if not ai_chars:
        return current_chars
    current_by_name = {c.get("name", "").lower(): i for i, c in enumerate(current_chars)}
    result = list(current_chars)
    for ai_c in ai_chars:
        key = ai_c.get("name", "").lower()
        if key in current_by_name:
            idx = current_by_name[key]
            result[idx] = {**result[idx], **ai_c}  # current fields as base, AI fields on top
        else:
            result.append(ai_c)
    return result


def _apply_rp_notes_updates(data: dict) -> list:
    """Append AI-proposed RP observations to character rp_notes in game_state and DB.
    Returns list of {name, note} dicts for client notification."""
    updates = data.get("rp_notes_updates") or []
    applied = []
    cid = state.get("campaign_id") or 0
    chars_by_name = {c.get("name", "").lower(): c for c in state["game_state"]["characters"]}
    for upd in updates:
        name = (upd.get("name") or "").strip()
        note = (upd.get("note") or "").strip()
        if not name or not note:
            continue
        char = chars_by_name.get(name.lower())
        if not char:
            continue
        existing = (char.get("rp_notes") or "").strip()
        char["rp_notes"] = (existing + "\n" + note).strip() if existing else note
        if char.get("name"):
            upsert_character(char, cid)
        applied.append({"name": char["name"], "note": note})
    if applied:
        _rebuild_party_context()
    return applied


def _apply_faction_mentions(data: dict) -> list:
    """Auto-create any newly mentioned factions and link NPC members.
    Returns list of {name, org_id, is_new} dicts for client notification."""
    mentions = data.get("faction_mentions") or []
    cid = state.get("campaign_id") or 0
    results = []
    existing_orgs = {o["name"].lower(): o for o in list_orgs(cid)}
    for m in mentions:
        name = (m.get("name") or "").strip()
        if not name:
            continue
        is_new = name.lower() not in existing_orgs
        if is_new:
            org_id = create_org(
                campaign_id  = cid,
                name         = name,
                org_type     = m.get("org_type", "other"),
                description  = m.get("description", ""),
                headquarters = m.get("headquarters", ""),
            )
            existing_orgs[name.lower()] = {"id": org_id, "name": name}
        else:
            org_id = existing_orgs[name.lower()]["id"]
        # Link any NPC members revealed this turn
        for npc_name in (m.get("npc_members") or []):
            npc_name = npc_name.strip()
            if not npc_name:
                continue
            npc = get_npc_by_name(cid, npc_name)
            if npc:
                add_org_member(org_id, cid, "npc", str(npc["id"]))
        results.append({"name": name, "org_id": org_id, "is_new": is_new})
    return results


def _build_portrait_prompt(char: dict) -> str:
    """Construct an Imagen prompt from character data."""
    race  = (char.get("race", "") or "").strip()
    name  = (char.get("name", "") or "adventurer").strip()
    notes = (char.get("notes",    "") or "").strip()
    rp    = (char.get("rp_notes", "") or "").strip()
    classes = char.get("classes") or []
    if classes:
        cls_parts = " / ".join(filter(None, [
            (e.get("subclass") or "") + " " + (e.get("class") or "") for e in classes
        ])).strip()
    else:
        subclass = (char.get("subclass", "") or "").strip()
        cls      = (char.get("class",    "") or "").strip()
        cls_parts = " ".join(filter(None, [subclass, cls]))

    subject = " ".join(filter(None, [race, cls_parts])) or "adventurer"
    flavor  = notes[:120] if notes else (rp.split("\n")[0][:120] if rp else "")

    parts = [
        f"Fantasy RPG character portrait of a {subject} named {name}.",
        flavor + "." if flavor else "",
        "Painterly digital art, close-up bust, dramatic lighting, detailed face,",
        "high quality D&D 5e character art, no text, no watermarks.",
    ]
    return " ".join(p for p in parts if p)


_STAT_ITEMS = [
    (re.compile(r'gauntlets of ogre (power|strength)',   re.I), 'str', 19),
    (re.compile(r'belt of hill giant strength',  re.I), 'str', 21),
    (re.compile(r'belt of stone giant strength', re.I), 'str', 23),
    (re.compile(r'belt of frost giant strength', re.I), 'str', 23),
    (re.compile(r'belt of fire giant strength',  re.I), 'str', 25),
    (re.compile(r'belt of cloud giant strength', re.I), 'str', 27),
    (re.compile(r'belt of storm giant strength', re.I), 'str', 29),
    (re.compile(r'gloves of dexterity',          re.I), 'dex', 19),
    (re.compile(r'amulet of health',             re.I), 'con', 19),
    (re.compile(r'headband of intellect',        re.I), 'int', 19),
    (re.compile(r'periapt of wisdom',            re.I), 'wis', 19),
    (re.compile(r'cloak of charisma',            re.I), 'cha', 18),
]

def _effective_stats(c: dict) -> dict:
    """Return effective ability scores, applying bonuses from equipped magic items."""
    STATS = ('str', 'dex', 'con', 'int', 'wis', 'cha')
    eff = {s: c.get(s, 10) for s in STATS}
    for item in (c.get('items') or []):
        if not isinstance(item, dict): continue
        slot = item.get('slot', '')
        if not slot or slot in ('', 'party_loot'): continue
        nm   = item.get('name', '')
        note = item.get('note', '') or ''
        for pattern, stat, val in _STAT_ITEMS:
            if pattern.search(nm):
                eff[stat] = max(eff[stat], val)
        for stat in STATS:
            m = re.search(rf'\b{stat}\s*\+\s*(\d+)', note, re.IGNORECASE)
            if m:
                eff[stat] += int(m.group(1))
    return eff


def _class_display(c: dict) -> str:
    """Return class string like 'Fighter 5 / Rogue 3' from classes array, or fallback to char_class."""
    classes = c.get("classes") or []
    if classes:
        parts = []
        for entry in classes:
            cls = (entry.get("class") or "").strip()
            lvl = entry.get("level") or 0
            sub = (entry.get("subclass") or "").strip()
            if cls:
                parts.append(f"{cls}{' (' + sub + ')' if sub else ''} {lvl}" if lvl else cls)
        return " / ".join(parts)
    cls = c.get("class", "")
    sub = c.get("subclass", "")
    lvl = c.get("level", 1)
    return f"{cls}{' (' + sub + ')' if sub else ''} {lvl}" if cls else ""


def _rebuild_party_context():
    """Rebuild the party_context string from current game_state characters."""
    lines = []
    for c in state["game_state"].get("characters", []):
        eff = _effective_stats(c)
        name = c.get('name', '')
        nickname = c.get('nickname', '').strip()
        display = f"{name} (goes by {nickname})" if nickname else name
        total_level = sum(e.get("level", 0) for e in (c.get("classes") or [])) or c.get("level", 1)
        line = (f"{display} | {c.get('race','')} {_class_display(c)}"
                f" Lv{total_level} | HP {c.get('hp',0)}/{c.get('max_hp',0)} AC {c.get('ac',0)}"
                f" | STR {eff['str']} DEX {eff['dex']} CON {eff['con']}"
                f" INT {eff['int']} WIS {eff['wis']} CHA {eff['cha']}")
        items = c.get("items") or []
        equipped = [f"{i['name']} [{i['slot']}]" for i in items
                    if isinstance(i, dict) and i.get('slot') and i['slot'] not in ('', 'party_loot')]
        carried  = [i['name'] if isinstance(i, dict) else str(i) for i in items
                    if isinstance(i, dict) and not i.get('slot')]
        if equipped:
            line += f" | Equipped: {', '.join(equipped)}"
        if carried:
            line += f" | Carried: {', '.join(carried[:6])}"
        rp = c.get('rp_notes', '').strip()
        if rp:
            line += f" | RP: {rp}"
        lines.append(line)
    state["party_context"] = "\n".join(lines)


def save_session():
    if not state["session_key"]:
        state["session_key"] = _new_session_key()
    db_save_session(
        session_key=state["session_key"],
        campaign_id=state["campaign_id"] or 0,
        turn=state["turn"],
        game_state=state["game_state"],
        history=_history_to_json(),
        combat_active=state.get("combat_active", False),
        session_mode=state.get("session_mode", "narrative"),
        combat_ui_state=state.get("combat_ui_state", {}),
        party_loot=state.get("party_loot", []),
    )


def load_session(session_key: str):
    row = db_load_session(session_key)
    if not row:
        return
    state["history"] = [
        types.Content(role=i["role"], parts=[types.Part(text=p["text"]) for p in i["parts"]])
        for i in row["history"]
    ]
    state["turn"]          = row["turn"]
    state["session_key"]   = session_key
    state["campaign_id"]   = row["campaign_id"]
    state["chronicle"]     = db_read_chronicle(session_key)
    campaign = get_campaign(row["campaign_id"])
    state["campaign_name"] = campaign["name"] if campaign else ""
    state["game_state"].update({
        "game_date":  row["game_date"],
        "location":   row["location"],
        "gold":       row["gold"],
        "xp":         row["xp"],
        "characters": read_main_tab_characters(row["campaign_id"]),
    })
    state["combat_active"]   = bool(row.get("combat_active", 0))
    state["session_mode"]    = row.get("session_mode", "narrative") or "narrative"
    state["combat_ui_state"] = row.get("combat_ui_state", {}) or {}
    state["party_loot"]      = row.get("party_loot", []) or []


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.before_request
def _set_campaign_context():
    """Route every HTTP request to the correct campaign's state automatically."""
    cid = (flask_session.get("gm_campaign_id")
           or flask_session.get("player_campaign")
           or 0)
    _thread_cid.id = int(cid) if cid else 0


@app.route("/health")
def health():
    return jsonify({"ok": True, "campaigns_loaded": len(_states_store)})


@app.route("/")
def index():
    if flask_session.get("gm_logged_in"):
        return redirect(url_for("gm_index"))
    return render_template("landing.html")


@app.route("/gm/login", methods=["GET", "POST"])
def gm_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == GM_PASSWORD:
            flask_session["gm_logged_in"] = True
            return redirect(url_for("gm_index"))
        error = "Incorrect password."
    return render_template("gm_login.html", error=error)


@app.route("/gm/logout")
def gm_logout():
    flask_session.pop("gm_logged_in", None)
    return redirect(url_for("gm_login"))


@app.route("/dm/")
@gm_required
def gm_index():
    resp = app.make_response(render_template("dm_session.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/campaigns")
def get_campaigns():
    return jsonify(list_campaigns())


@app.route("/new-campaign", methods=["POST"])
def new_campaign():
    name = request.json.get("name", "").strip()
    description = request.json.get("description", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Campaign name required"})
    try:
        cid = create_campaign(name, description)
        flask_session["gm_campaign_id"] = cid
        _thread_cid.id = cid
        state.update({
            "history": [], "turn": 0, "session_key": _new_session_key(),
            "campaign_id": cid, "campaign_name": name, "party_context": "",
            "game_state": {"gold": 0, "xp": 0, "game_date": "", "location": "", "characters": []},
            "chronicle": [],
        })
        return jsonify({"ok": True, "campaign_id": cid, "campaign_name": name})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/sessions")
def list_sessions():
    campaign_id = request.args.get("campaign_id", type=int)
    if campaign_id is None:
        return jsonify({"ok": False, "error": "campaign_id required"})
    rows = db_list_sessions(campaign_id)
    return jsonify([{
        "filename":   r["session_key"],
        "name":       r["name"] or r["session_key"],
        "turn":       r["turn"],
        "last_saved": (r["last_saved"] or "")[:16].replace("T", " "),
        "location":   r["location"],
        "game_date":  r["game_date"],
    } for r in rows])


@app.route("/load-session", methods=["POST"])
def load_session_route():
    session_key = request.json.get("filename", "")
    try:
        load_session(session_key)
        cid = state["campaign_id"] or 0
        flask_session["gm_campaign_id"] = cid
        _thread_cid.id = cid
        return jsonify({"ok": True, "turn": state["turn"],
                        "game_state":     state["game_state"],
                        "chronicle":      state["chronicle"],
                        "campaign_id":    state["campaign_id"],
                        "campaign_name":  state["campaign_name"],
                        "combat_active":  state["combat_active"],
                        "session_mode":   state["session_mode"],
                        "combat_ui":      state.get("combat_ui_state", {}),
                        "party_loot":     state.get("party_loot", [])})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/new-session", methods=["POST"])
def new_session():
    # Accept campaign_id from client (needed when starting a fresh session
    # without a prior load-session call setting state["campaign_id"])
    body = request.json or {}
    cid_from_client = body.get("campaign_id")
    if cid_from_client:
        state["campaign_id"] = int(cid_from_client)
        campaign = get_campaign(state["campaign_id"])
        state["campaign_name"] = campaign["name"] if campaign else ""
    cid = state.get("campaign_id") or 0
    state.update({
        "history": [], "turn": 0, "session_key": _new_session_key(), "party_context": "",
        "game_state": {
            "gold": 0, "xp": 0, "game_date": "", "location": "",
            "characters": read_main_tab_characters(cid),
        },
        "chronicle": [],
    })
    return jsonify({"ok": True, "campaign_id": state["campaign_id"],
                    "campaign_name": state["campaign_name"]})


@app.route("/correct", methods=["POST"])
def correct():
    """
    Inject a correction into the session history without logging to chronicle
    or generating a story entry. Gemini acknowledges and updates game state.
    Use this to fix factual errors mid-session (wrong HP, wrong target, etc.).
    """
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"ok": False, "error": "Empty message"})

    tagged = (
        f"[CORRECTION — not a game action, do not advance the story] "
        f"{user_input}. "
        f"Acknowledge the correction briefly, update your game state accordingly, "
        f"and confirm what has changed."
    )
    state["history"].append(
        types.Content(role="user", parts=[types.Part(text=tagged)])
    )

    session_mode = request.json.get("session_mode", "narrative")

    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=state["history"],
            config=types.GenerateContentConfig(
                system_instruction=build_system(state["party_context"], session_mode),
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        state["history"].pop()
        return jsonify({"ok": False, "error": str(e)})

    data = parse_dm_response(response.text)
    if not data:
        state["history"].pop()
        return jsonify({"ok": False, "error": "Bad JSON from Gemini", "raw": response.text})

    _log_usage("correct", response)
    state["history"].append(
        types.Content(role="model", parts=[types.Part(text=response.text)])
    )

    # Update game state from the corrected response
    gs = data.get("game_state", {})
    state["game_state"].update({
        "gold":       gs.get("gold",       state["game_state"]["gold"]),
        "xp":         gs.get("xp",         state["game_state"].get("xp", 0)),
        "game_date":  data.get("game_date", state["game_state"]["game_date"]),
        "location":   gs.get("location",   state["game_state"]["location"]),
        "characters": _merge_ai_characters(gs.get("characters"), state["game_state"]["characters"]),
    })

    # Persist AI-updated character fields back to characters table
    _cid = state.get("campaign_id") or 0
    for _c in state["game_state"]["characters"]:
        if _c.get("name"):
            upsert_character(_c, _cid)
    _rebuild_party_context()

    rp_updates = _apply_rp_notes_updates(data)
    faction_updates = _apply_faction_mentions(data)

    # Save history to DB but skip chronicle and story
    save_session()

    return jsonify({
        "ok":               True,
        "dm_response":      data.get("dm_response", ""),
        "game_state":       state["game_state"],
        "combat_updates":   data.get("combat_updates", []),
        "map_layout":       data.get("map_layout"),
        "rp_notes_updates": rp_updates,
        "new_factions":     faction_updates,
    })


@app.route("/chat", methods=["POST"])
def chat():
    user_input     = request.json.get("message", "").strip()
    session_mode   = request.json.get("session_mode", "narrative")
    combat_context = request.json.get("combat_context", "")
    if not user_input:
        return jsonify({"ok": False, "error": "Empty message"})

    state["turn"] += 1
    sync_id = generate_sync_id(state["turn"])
    state["history"].append(
        types.Content(role="user", parts=[types.Part(text=f"[sync_id: {sync_id}]\n{user_input}")])
    )

    cid = state.get("campaign_id") or 0
    current_location = state["game_state"].get("location", "")
    location_npcs = get_npcs_at_location(cid, current_location) if current_location else []

    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=state["history"],
            config=types.GenerateContentConfig(
                system_instruction=build_system(state["party_context"], session_mode, combat_context, location_npcs),
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        state["history"].pop()
        state["turn"] -= 1
        return jsonify({"ok": False, "error": str(e)})

    data = parse_dm_response(response.text)
    if not data:
        state["history"].pop()
        state["turn"] -= 1
        return jsonify({"ok": False, "error": "Gemini returned invalid JSON", "raw": response.text})

    _log_usage("chat", response)
    state["history"].append(
        types.Content(role="model", parts=[types.Part(text=response.text)])
    )

    gs = data.get("game_state", {})
    state["game_state"].update({
        "gold":       gs.get("gold",       state["game_state"]["gold"]),
        "xp":         gs.get("xp",         state["game_state"].get("xp", 0)),
        "game_date":  data.get("game_date", state["game_state"]["game_date"]),
        "location":   gs.get("location",   state["game_state"]["location"]),
        "characters": _merge_ai_characters(gs.get("characters"), state["game_state"]["characters"]),
    })

    # Persist AI-updated character fields (HP, AC, status, buffs/debuffs) back to characters table
    _cid = state.get("campaign_id") or 0
    for _c in state["game_state"]["characters"]:
        if _c.get("name"):
            upsert_character(_c, _cid)
    _rebuild_party_context()

    rp_updates = _apply_rp_notes_updates(data)
    faction_updates = _apply_faction_mentions(data)

    entry = {
        "sync_id":   sync_id,
        "game_date": data.get("game_date", ""),
        "player":    data.get("player_restatement", user_input),
        "dm":        data.get("dm_response", ""),
    }
    state["chronicle"].append(entry)
    if not state["session_key"]:
        state["session_key"] = _new_session_key()
    # Auto-save everything to DB every turn
    save_session()
    cid = state["campaign_id"] or 0

    # Process NPC updates from AI response
    npc_results = []
    for upd in data.get("npc_updates", []):
        name = (upd.get("name") or "").strip()
        if not name:
            continue
        try:
            npc = upsert_npc(
                campaign_id=cid,
                name=name,
                npc_type=upd.get("npc_type", ""),
                attitude_delta=int(upd.get("attitude_delta", 0)),
                location=upd.get("location", ""),
                notes=upd.get("notes", ""),
                last_seen_date=data.get("game_date", ""),
                last_seen_loc=state["game_state"].get("location", ""),
            )
            for offer in upd.get("new_offers", []):
                add_npc_offer(
                    npc_id=npc["id"],
                    campaign_id=cid,
                    offer_type=offer.get("offer_type", "item"),
                    title=offer.get("title", ""),
                    description=offer.get("description", ""),
                    price_gp=offer.get("price_gp"),
                    created_date=data.get("game_date", ""),
                    expires_date=offer.get("expires_date", ""),
                )
            npc_results.append(npc)
        except Exception as e:
            log.warning("NPC update failed for '%s': %s", name, e)
    append_chronicle(
        session_key=state["session_key"],
        campaign_id=cid,
        sync_id=sync_id,
        game_date=data.get("game_date", ""),
        player_text=data.get("player_restatement", user_input),
        dm_text=data.get("dm_response", ""),
        user_raw=user_input,
    )

    threading.Thread(
        target=_write_story_entry,
        args=(state["session_key"], cid, sync_id, data.get("game_date", ""),
              data.get("player_restatement", user_input),
              data.get("dm_response", ""),
              state["game_state"].get("location", ""),
              state["model"]),
        daemon=True,
    ).start()

    ai_session_mode = data.get("session_mode", "").strip().lower()
    if ai_session_mode in ("combat", "roleplay", "narrative"):
        state["session_mode"] = ai_session_mode

    # Process loot awards — append to session party loot pool
    new_loot = []
    for award in data.get("loot_awards", []):
        name = (award.get("name") or "").strip()
        if not name:
            continue
        entry = {
            "id":       str(uuid.uuid4())[:8],
            "name":     name,
            "qty":      int(award.get("qty") or 1),
            "value_gp": int(award.get("value_gp") or 0),
            "notes":    str(award.get("notes") or ""),
        }
        state["party_loot"].append(entry)
        new_loot.append(entry)
    if new_loot:
        save_session()

    # Broadcast map to players if AI updated it
    if data.get("map_layout"):
        broadcast_map_update(map_layout=data["map_layout"])

    return jsonify({
        "ok":               True,
        "sync_id":          sync_id,
        "game_date":        data.get("game_date", ""),
        "player_text":      data.get("player_restatement", user_input),
        "dm_response":      data.get("dm_response", ""),
        "game_state":       state["game_state"],
        "user_raw":         user_input,
        "npc_updates":      npc_results,
        "session_mode":     state["session_mode"],
        "combat_updates":   data.get("combat_updates", []),
        "map_layout":       data.get("map_layout"),
        "loot_awards":      new_loot,
        "party_loot":       state["party_loot"],
        "rp_notes_updates": rp_updates,
        "new_factions":     faction_updates,
    })


@app.route("/save-turn", methods=["POST"])
def save_turn():
    if not state["chronicle"]:
        return jsonify({"ok": False, "error": "No turns to save"})
    entry    = state["chronicle"][-1]
    user_raw = request.json.get("user_raw", "")
    turn_data = {
        "sync_id":            entry["sync_id"],
        "game_date":          entry["game_date"],
        "player_restatement": entry["player"],
        "dm_response":        entry["dm"],
    }
    try:
        append_session_entry(turn_data, user_raw)
        update_from_session(state["game_state"], entry["sync_id"], entry["game_date"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/load-party", methods=["POST"])
def load_party():
    try:
        characters = read_main_tab_characters(state["campaign_id"] or 0)
        if not characters:
            return jsonify({"ok": False, "error": "No characters found in Main tab"})
        state["game_state"]["characters"] = characters
        _rebuild_party_context()
        save_session()
        return jsonify({"ok": True, "characters": characters})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/scrape-character", methods=["POST"])
def scrape_character():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "No URL"})
    if not HAS_REQUESTS:
        return jsonify({"ok": False, "error": "pip install requests"})
    try:
        r    = http_req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        html = r.text
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    # D&D Beyond embeds character data in __NEXT_DATA__ JSON — use that if available
    next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if next_data:
        source = "NEXT_DATA JSON: " + next_data.group(1)[:40000]
    else:
        source = "HTML: " + html[:20000]

    prompt = f"""Extract D&D 5e character data from this page source. Return ONLY valid JSON:
{{
  "name":"","race":"","class":"","level":1,"hp":0,"max_hp":0,"ac":0,
  "stats":{{"str":0,"dex":0,"con":0,"int":0,"wis":0,"cha":0}},
  "weapons":[],"spells":[],"features":[],"background":"","alignment":""
}}
{source}"""

    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        char = json.loads(response.text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    stats = char.get("stats", {})
    ctx   = (f"{char.get('name')} | {char.get('race')} {char.get('class')} Lv{char.get('level')} | "
             f"HP {char.get('hp')}/{char.get('max_hp')} AC {char.get('ac')} | "
             f"STR {stats.get('str')} DEX {stats.get('dex')} CON {stats.get('con')} "
             f"INT {stats.get('int')} WIS {stats.get('wis')} CHA {stats.get('cha')}")
    if char.get("weapons"):
        ctx += f" | Weapons: {', '.join(char['weapons'])}"
    state["party_context"] += ctx + "\n"

    # Add to game_state characters (avoid duplicates by name)
    new_char = {
        "name":    char.get("name", ""),
        "class":   char.get("class", ""),
        "level":   char.get("level", 1),
        "hp":      char.get("hp", 0),
        "max_hp":  char.get("max_hp", 0),
        "ac":      char.get("ac", 0),
        "buffs":   [],
        "debuffs": [],
    }
    existing = state["game_state"]["characters"]
    names = [c["name"].lower() for c in existing]
    if new_char["name"].lower() not in names:
        existing.append(new_char)
    else:
        # Update existing entry
        for i, c in enumerate(existing):
            if c["name"].lower() == new_char["name"].lower():
                existing[i] = new_char
                break

    return jsonify({"ok": True, "character": char})


@app.route("/ooc-chat", methods=["POST"])
def ooc_chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"ok": False, "error": "Empty message"})

    gs = state["game_state"]

    char_lines = []
    for c in gs.get("characters", []):
        line = (
            f"  {c.get('name')} | {c.get('race','')} {c.get('class','')} {c.get('subclass','')}"
            f" Lv{c.get('level',1)} | HP {c.get('hp',0)}/{c.get('max_hp',0)} AC {c.get('ac',0)}"
            f" Speed {c.get('speed','')} | Status: {c.get('status','')}"
            f" | STR {c.get('str',0)} DEX {c.get('dex',0)} CON {c.get('con',0)}"
            f" INT {c.get('int',0)} WIS {c.get('wis',0)} CHA {c.get('cha',0)}"
        )
        if c.get("items"):
            line += f" | Items: {', '.join(c['items'])}"
        if c.get("buffs"):
            line += f" | Buffs: {', '.join(c['buffs'])}"
        if c.get("debuffs"):
            line += f" | Debuffs: {', '.join(c['debuffs'])}"
        if c.get("notes"):
            line += f" | Notes: {c['notes']}"
        char_lines.append(line)

    party_block = "\n".join(char_lines) if char_lines else "  (none)"

    ooc_system = (
        "You are assisting a developer building and QA-testing a D&D 5e DM web application. "
        "Answer any question directly and helpfully — about the code, the session data, "
        "D&D rules, or anything else asked. Respond in plain text.\n\n"
        f"SESSION: location={gs.get('location','unknown')}, date={gs.get('game_date','unknown')}, "
        f"gold={gs.get('gold',0)} gp, xp={gs.get('xp',0)}\n\n"
        f"PARTY:\n{party_block}"
    )
    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=state["history"] + [
                types.Content(role="user", parts=[types.Part(text=user_input)])
            ],
            config=types.GenerateContentConfig(system_instruction=ooc_system),
        )
        _log_usage("ooc_chat", response)
        return jsonify({"ok": True, "response": response.text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/update-character", methods=["POST"])
def update_character():
    data          = request.json
    original_name = data.get("original_name", "")
    updated       = data.get("character", {})
    cid           = state.get("campaign_id") or 0
    characters    = state["game_state"]["characters"]
    for i, c in enumerate(characters):
        if c.get("name", "").lower() == original_name.lower():
            characters[i] = updated
            upsert_character(updated, cid)
            _rebuild_party_context()
            save_session()
            return jsonify({"ok": True, "characters": characters})
    # Not found — append as new
    characters.append(updated)
    upsert_character(updated, cid)
    # Seed spellbook when creating a brand-new character via the wizard
    if not original_name:
        spell_list    = updated.get("spells", [])
        cantrip_names = [s["name"] for s in spell_list if isinstance(s, dict) and s.get("level") == 0]
        spell_names   = [s["name"] for s in spell_list if isinstance(s, dict) and s.get("level", 0) > 0]
        seed_spellbook_from_names(cid, updated.get("name", ""), spell_names, cantrip_names)
    _rebuild_party_context()
    save_session()
    return jsonify({"ok": True, "characters": characters})


@app.route("/character/delete", methods=["POST"])
def character_delete():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Missing name"}), 400
    cid = state.get("campaign_id") or 0
    state["game_state"]["characters"] = [
        c for c in state["game_state"]["characters"]
        if c.get("name", "").lower() != name.lower()
    ]
    delete_character(name, cid)
    _rebuild_party_context()
    save_session()
    return jsonify({"ok": True, "characters": state["game_state"]["characters"]})


# ── Portrait routes ────────────────────────────────────────────────────────────

@app.route("/portraits/<path:filename>")
def serve_portrait(filename):
    return send_from_directory(PORTRAITS_DIR, filename)


@app.route("/character/portrait/upload", methods=["POST"])
def portrait_upload():
    name = request.form.get("name", "").strip()
    if not name or "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing name or file"})
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"})
    ext = os.path.splitext(f.filename)[1].lower() or ".png"
    slug = re.sub(r"[^\w]", "_", name.lower())
    filename = f"{slug}{ext}"
    f.save(os.path.join(PORTRAITS_DIR, filename))
    cid = state.get("campaign_id") or 0
    set_character_portrait(name, cid, filename)
    # Update in-memory game state
    for c in state["game_state"]["characters"]:
        if c.get("name", "").lower() == name.lower():
            c["portrait_path"] = filename
            break
    return jsonify({"ok": True, "portrait_path": filename, "url": f"/portraits/{filename}"})


@app.route("/character/portrait/suggest", methods=["POST"])
def portrait_suggest():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Missing character name"})
    char = next(
        (c for c in state["game_state"]["characters"] if c.get("name", "").lower() == name.lower()),
        None,
    )
    if not char:
        return jsonify({"ok": False, "error": f"Character '{name}' not found in session"})
    prompt = _build_portrait_prompt(char)
    try:
        client = genai.Client(api_key=get_api_key())
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_low_and_above",
                person_generation="allow_adult",
            ),
        )
        img_bytes = result.generated_images[0].image.image_bytes
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    slug = re.sub(r"[^\w]", "_", name.lower())
    filename = f"{slug}.png"
    with open(os.path.join(PORTRAITS_DIR, filename), "wb") as fh:
        fh.write(img_bytes)
    cid = state.get("campaign_id") or 0
    set_character_portrait(name, cid, filename)
    for c in state["game_state"]["characters"]:
        if c.get("name", "").lower() == name.lower():
            c["portrait_path"] = filename
            break
    log_api_call(state.get("session_key",""), cid, "portrait_image",
                 "imagen-4.0-generate-001", 0, 0,
                 user_id=current_user.id if current_user.is_authenticated else None)
    return jsonify({"ok": True, "portrait_path": filename, "url": f"/portraits/{filename}"})


@app.route("/game-state")
def game_state():
    gs = dict(state["game_state"])
    gs["session_key"]    = state.get("session_key")
    gs["campaign_id"]    = state.get("campaign_id")
    gs["campaign_name"]  = state.get("campaign_name", "")
    gs["combat_active"]  = state.get("combat_active", False)
    gs["session_mode"]   = state.get("session_mode", "narrative")
    gs["combat_ui"]      = state.get("combat_ui_state", {})
    gs["party_loot"]     = state.get("party_loot", [])
    gs["chronicle"]      = state.get("chronicle", [])
    return jsonify(gs)


# ── Magic items routes ─────────────────────────────────────────────────────────

# ── Mob routes ─────────────────────────────────────────────────────────────────

@app.route("/mobs/search")
def mobs_search():
    q     = request.args.get("q", "").strip()
    limit = request.args.get("limit", 12, type=int)
    return jsonify(search_mobs(query=q, limit=limit))


@app.route("/mobs/get")
def mobs_get():
    name = request.args.get("name", "").strip()
    mob  = get_mob(name)
    if not mob:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(mob)


@app.route("/mobs/count")
def mobs_count():
    return jsonify({"count": count_mobs()})


@app.route("/mob-images/<path:filename>")
def serve_mob_image(filename):
    return send_from_directory(MOB_IMAGES_DIR, filename)


@app.route("/mobs/image/upload", methods=["POST"])
def mob_image_upload():
    name = request.form.get("name", "").strip()
    if not name or "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing name or file"})
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"})
    ext      = os.path.splitext(f.filename)[1].lower() or ".png"
    slug     = re.sub(r"[^\w]", "_", name.lower())
    filename = f"{slug}{ext}"
    f.save(os.path.join(MOB_IMAGES_DIR, filename))
    set_mob_image(name, filename)
    return jsonify({"ok": True, "image_path": filename, "url": f"/mob-images/{filename}"})


@app.route("/mobs/image/suggest", methods=["POST"])
def mob_image_suggest():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Missing mob name"})
    mob = get_mob(name)
    size     = (mob.get("size",     "") or "") if mob else ""
    mob_type = (mob.get("mob_type", "") or "") if mob else ""
    alignment= (mob.get("alignment","") or "") if mob else ""
    desc     = (mob.get("description","") or "") if mob else ""
    subject  = " ".join(filter(None, [size, alignment, mob_type, name]))
    flavor   = desc[:120] if desc else ""
    prompt   = (
        f"Fantasy RPG creature portrait of a {subject}. "
        + (flavor + ". " if flavor else "")
        + "Painterly digital art, full creature visible, dramatic lighting, "
        + "high quality D&D 5e monster art, no text, no watermarks."
    )
    try:
        client = genai.Client(api_key=get_api_key())
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_low_and_above",
                person_generation="allow_adult",
            ),
        )
        img_bytes = result.generated_images[0].image.image_bytes
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    slug     = re.sub(r"[^\w]", "_", name.lower())
    filename = f"{slug}.png"
    with open(os.path.join(MOB_IMAGES_DIR, filename), "wb") as fh:
        fh.write(img_bytes)
    set_mob_image(name, filename)
    log_api_call(state.get("session_key",""), state.get("campaign_id") or 0,
                 "mob_image", "imagen-4.0-generate-001", 0, 0,
                 user_id=current_user.id if current_user.is_authenticated else None)
    return jsonify({"ok": True, "image_path": filename, "url": f"/mob-images/{filename}"})


@app.route("/mobs/languages", methods=["POST"])
def mob_set_languages():
    data  = request.json or {}
    name  = data.get("name", "").strip()
    langs = data.get("languages", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Missing mob name"})
    update_mob_languages(name, langs)
    return jsonify({"ok": True})


# ── Monster Manual routes ──────────────────────────────────────────────────────

@app.route("/monster-manual/list")
def monster_manual_list():
    cid = state.get("campaign_id") or 0
    return jsonify(list_mobs_for_manual(cid))


@app.route("/monster-manual/get")
def monster_manual_get():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Missing name"}), 400
    mob = get_mob(name)
    if not mob:
        return jsonify({"ok": False, "error": "Not found"}), 404
    cid = state.get("campaign_id") or 0
    mob["knowledge_rank"] = get_mob_knowledge(name, cid)["knowledge_rank"]
    mob["knowledge_notes"] = get_mob_knowledge(name, cid)["notes"]
    return jsonify(mob)


@app.route("/monster-manual/set-rank", methods=["POST"])
def monster_manual_set_rank():
    data = request.json or {}
    name = data.get("name", "").strip()
    rank = data.get("rank", "unknown")
    notes = data.get("notes")
    if not name:
        return jsonify({"ok": False, "error": "Missing name"}), 400
    cid = state.get("campaign_id") or 0
    set_mob_knowledge(name, cid, rank, notes)
    return jsonify({"ok": True})


@app.route("/monster-manual/advance-rank", methods=["POST"])
def monster_manual_advance_rank():
    data = request.json or {}
    name = data.get("name", "").strip()
    min_rank = data.get("min_rank", "seen")
    if not name:
        return jsonify({"ok": False, "error": "Missing name"}), 400
    cid = state.get("campaign_id") or 0
    advance_mob_knowledge(name, cid, min_rank)
    return jsonify({"ok": True, "rank": get_mob_knowledge(name, cid)["knowledge_rank"]})


@app.route("/magic-items/search")
def magic_items_search():
    q        = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    rarity   = request.args.get("rarity", "").strip()
    limit    = request.args.get("limit", 20, type=int)
    results  = search_magic_items(query=q, category=category, rarity=rarity, limit=limit)
    return jsonify(results)


@app.route("/magic-items/count")
def magic_items_count():
    return jsonify({"count": count_magic_items()})


@app.route("/mundane-items/search")
def mundane_items_search():
    q          = request.args.get("q", "").strip()
    category   = request.args.get("category", "").strip()
    store_type = request.args.get("store_type", "").strip()
    limit      = request.args.get("limit", 12, type=int)
    results    = search_mundane_items(query=q, category=category,
                                      store_type=store_type, limit=limit)
    return jsonify(results)


# ── Spell routes ───────────────────────────────────────────────────────────────

@app.route("/spells/search")
def spells_search():
    q          = request.args.get("q", "").strip()
    level      = request.args.get("level", type=int)
    school     = request.args.get("school", "").strip()
    char_class = request.args.get("char_class", "").strip()
    results = search_spells_reference(query=q, level=level, school=school,
                                      char_class=char_class)
    return jsonify(results)


@app.route("/spells/reference-count")
def spells_reference_count():
    return jsonify({"count": count_spells_reference()})


@app.route("/spells/sources")
def spells_sources():
    return jsonify(list_spell_sources())


@app.route("/spells/sources/toggle", methods=["POST"])
def spells_sources_toggle():
    source  = request.json.get("source", "").strip()
    enabled = bool(request.json.get("enabled", True))
    if not source:
        return jsonify({"ok": False, "error": "source required"})
    set_source_enabled(source, enabled)
    return jsonify({"ok": True})


@app.route("/spells/book")
def spells_book():
    cid       = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    char_name = request.args.get("char_name", "").strip()
    if not char_name:
        return jsonify({"ok": False, "error": "char_name required"})
    return jsonify(get_spellbook(cid, char_name))


@app.route("/spells/book/add", methods=["POST"])
def spells_book_add():
    data      = request.json
    cid       = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = data.get("char_name", "").strip()
    spell_id  = data.get("spell_id")
    prepared  = bool(data.get("prepared", False))
    notes     = data.get("notes", "")
    if not char_name or not spell_id:
        return jsonify({"ok": False, "error": "char_name and spell_id required"})
    ok = add_to_spellbook(cid, char_name, spell_id, prepared, notes)
    return jsonify({"ok": ok})


@app.route("/spells/book/remove", methods=["POST"])
def spells_book_remove():
    data      = request.json
    cid       = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = data.get("char_name", "").strip()
    spell_id  = data.get("spell_id")
    if not char_name or not spell_id:
        return jsonify({"ok": False, "error": "char_name and spell_id required"})
    remove_from_spellbook(cid, char_name, spell_id)
    return jsonify({"ok": True})


@app.route("/spells/book/prepared", methods=["POST"])
def spells_book_prepared():
    data      = request.json
    cid       = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = data.get("char_name", "").strip()
    spell_id  = data.get("spell_id")
    prepared  = bool(data.get("prepared", False))
    if not char_name or not spell_id:
        return jsonify({"ok": False, "error": "char_name and spell_id required"})
    set_spell_prepared(cid, char_name, spell_id, prepared)
    return jsonify({"ok": True})


@app.route("/spells/book/notes", methods=["POST"])
def spells_book_notes():
    data      = request.json
    cid       = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = data.get("char_name", "").strip()
    spell_id  = data.get("spell_id")
    notes     = data.get("notes", "")
    if not char_name or not spell_id:
        return jsonify({"ok": False, "error": "char_name and spell_id required"})
    update_spellbook_notes(cid, char_name, spell_id, notes)
    return jsonify({"ok": True})


# ── Calendar routes ────────────────────────────────────────────────────────────

@app.route("/calendar")
def calendar_full():
    leap = request.args.get("leap", "false").lower() == "true"
    return jsonify(get_calendar_full(include_leap_day=leap))


@app.route("/calendar/<int:day>")
def calendar_day(day):
    row = get_calendar_day(day)
    if not row:
        return jsonify({"error": "Day not found"}), 404
    return jsonify(row)


@app.route("/calendar/current")
def calendar_current():
    """Return calendar info for the session's current game_date (if it's a day number)."""
    game_date = state["game_state"].get("game_date", "")
    # Try to extract a day-of-year number from the stored game_date string
    import re
    match = re.search(r"\b(\d{1,3})\b", str(game_date))
    if not match:
        return jsonify({"ok": False, "error": "game_date is not a day number", "game_date": game_date})
    day = int(match.group(1))
    row = get_calendar_day(day)
    if not row:
        return jsonify({"ok": False, "error": f"Day {day} not in calendar"})
    return jsonify({"ok": True, "day": row, "game_date": game_date})


@app.route("/calendar/month/<path:name>")
def calendar_month(name):
    return jsonify(get_calendar_month(name))


@app.route("/calendar/advance", methods=["POST"])
def calendar_advance():
    data     = request.json
    days     = int(data.get("days", 1))
    leap     = bool(data.get("is_leap_year", False))
    # Use provided day or fall back to session game_date
    current  = data.get("current_day")
    if current is None:
        import re
        match = re.search(r"\b(\d{1,3})\b", str(state["game_state"].get("game_date", "")))
        current = int(match.group(1)) if match else 1
    row = advance_date(int(current), days, leap)
    if not row:
        return jsonify({"ok": False, "error": "Could not advance date"})
    # Optionally update session game_date
    if data.get("save", False):
        label = f"{row['month_short']} {row['day_of_month']}" if row["day_of_month"] else row["festival_name"]
        state["game_state"]["game_date"] = f"Day {row['day_of_year']} ({label})"
        save_session()
    return jsonify({"ok": True, "day": row})


# ── NPC routes ─────────────────────────────────────────────────────────────────

@app.route("/npcs")
def npcs_list():
    cid = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    npcs = list_npcs(cid)
    # Attach active offers to each NPC
    for npc in npcs:
        npc["offers"] = list_npc_offers(npc["id"], status="active")
    return jsonify(npcs)


@app.route("/npcs/upsert", methods=["POST"])
def npcs_upsert():
    data = request.json
    cid  = data.get("campaign_id") or state.get("campaign_id") or 0
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"})
    npc = upsert_npc(
        campaign_id=cid,
        name=name,
        npc_type=data.get("npc_type", ""),
        attitude_delta=0,        # manual edits use set_attitude instead
        faction=data.get("faction", ""),
        location=data.get("location", ""),
        notes=data.get("notes", ""),
        is_store=bool(data.get("is_store", False)),
    )
    # If an absolute attitude is provided, set it directly
    if "attitude" in data:
        set_npc_attitude(npc["id"], int(data["attitude"]))
        npc["attitude"] = max(-100, min(100, int(data["attitude"])))
    return jsonify({"ok": True, "npc": npc})


@app.route("/npcs/<int:npc_id>", methods=["DELETE"])
def npcs_delete(npc_id):
    delete_npc(npc_id)
    return jsonify({"ok": True})


@app.route("/npcs/<int:npc_id>/attitude", methods=["POST"])
def npcs_set_attitude(npc_id):
    attitude = request.json.get("attitude")
    if attitude is None:
        return jsonify({"ok": False, "error": "attitude required"})
    set_npc_attitude(npc_id, int(attitude))
    return jsonify({"ok": True})


@app.route("/npcs/<int:npc_id>/offers")
def npcs_offers(npc_id):
    status = request.args.get("status")  # optional filter
    return jsonify(list_npc_offers(npc_id, status=status))


@app.route("/npcs/<int:npc_id>/offers/add", methods=["POST"])
def npcs_offers_add(npc_id):
    data = request.json
    cid  = data.get("campaign_id") or state.get("campaign_id") or 0
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title required"})
    oid = add_npc_offer(
        npc_id=npc_id,
        campaign_id=cid,
        offer_type=data.get("offer_type", "item"),
        title=title,
        description=data.get("description", ""),
        price_gp=data.get("price_gp"),
        created_date=data.get("created_date", ""),
        expires_date=data.get("expires_date", ""),
    )
    return jsonify({"ok": True, "offer_id": oid})


@app.route("/npcs/offers/<int:offer_id>/status", methods=["POST"])
def npcs_offer_status(offer_id):
    status = (request.json.get("status") or "").strip()
    if status not in ("active", "sold", "resolved", "expired"):
        return jsonify({"ok": False, "error": "invalid status"})
    set_offer_status(offer_id, status)
    return jsonify({"ok": True})


@app.route("/npcs/offers/<int:offer_id>", methods=["DELETE"])
def npcs_offer_delete(offer_id):
    delete_offer(offer_id)
    return jsonify({"ok": True})


@app.route("/npcs/offers/<int:offer_id>/purchase", methods=["POST"])
def npcs_offer_purchase(offer_id):
    """Mark an offer as sold and return item details for frontend to add to inventory."""
    offer = get_offer(offer_id)
    if not offer:
        return jsonify({"ok": False, "error": "Offer not found"})
    if offer["status"] != "active":
        return jsonify({"ok": False, "error": "Offer is no longer active"})
    set_offer_status(offer_id, "sold")
    return jsonify({
        "ok": True,
        "item": {
            "name":     offer["title"],
            "qty":      1,
            "note":     offer["description"] or "",
            "slot":     "",
            "price_gp": offer["price_gp"],
        }
    })


@app.route("/npcs/active-offers")
def npcs_active_offers():
    cid = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    return jsonify(list_all_active_offers(cid))


# ── NPC Affinity ────────────────────────────────────────────────────────────────

@app.route("/npcs/<int:npc_id>/affinity")
def npcs_get_affinity(npc_id):
    cid = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    return jsonify(get_all_npc_affinities(cid, npc_id))


@app.route("/npcs/<int:npc_id>/affinity/set", methods=["POST"])
def npcs_set_affinity(npc_id):
    data = request.json
    cid = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = (data.get("char_name") or "").strip()
    score = data.get("score", 0)
    if not char_name:
        return jsonify({"ok": False, "error": "char_name required"})
    set_npc_affinity(cid, npc_id, char_name, int(score))
    return jsonify({"ok": True, "score": max(-100, min(100, int(score)))})


@app.route("/npcs/<int:npc_id>/affinity/adjust", methods=["POST"])
def npcs_adjust_affinity(npc_id):
    data = request.json
    cid = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = (data.get("char_name") or "").strip()
    delta = data.get("delta", 0)
    if not char_name:
        return jsonify({"ok": False, "error": "char_name required"})
    new_score = adjust_npc_affinity(cid, npc_id, char_name, int(delta))
    return jsonify({"ok": True, "score": new_score})


def _affinity_label(score: int) -> str:
    if score <= -61: return "Openly hostile"
    if score <= -21: return "Cold and guarded"
    if score <=  20: return "Indifferent"
    if score <=  60: return "Warm and welcoming"
    return "Deeply trusted"


def _price_modifier(score: int) -> float:
    """Returns a price multiplier based on affinity score."""
    if score <= -61: return 1.50
    if score <= -21: return 1.20
    if score <=  20: return 1.00
    if score <=  60: return 0.90
    return 0.80


def _build_npc_chat_system(npc: dict, speaking_char: dict, affinity: int,
                           campaign_id: int, org_ctx: dict = None) -> str:
    char_name = speaking_char.get("name", "Adventurer")
    char_class = speaking_char.get("char_class", "")
    cha_score = speaking_char.get("cha_score", 10)
    cha_mod = (cha_score - 10) // 2
    label = _affinity_label(affinity)
    npc_name = npc.get("name", "NPC")
    npc_type = (npc.get("npc_type") or "npc").replace("_", " ")
    npc_notes = npc.get("notes", "")
    all_chars = [c.get("name") for c in state["game_state"].get("characters", [])]

    # Build org context string
    org_block = ""
    if org_ctx and (org_ctx.get("char_orgs") or org_ctx.get("npc_orgs")):
        char_org_names = [o["name"] for o in (org_ctx.get("char_orgs") or [])]
        npc_org_names  = [o["name"] for o in (org_ctx.get("npc_orgs")  or [])]
        org_block = ""
        if char_org_names:
            org_block += f"\n{char_name} belongs to: {', '.join(char_org_names)}."
        if npc_org_names:
            org_block += f"\nYou ({npc_name}) belong to: {', '.join(npc_org_names)}."
        if org_ctx.get("pairs"):
            for p in org_ctx["pairs"]:
                rel = _affinity_label(p["score"])
                org_block += f"\n  [{p['char_org']}] ↔ [{p['npc_org']}]: {rel}."

    return f"""You are {npc_name}, a {npc_type} in a D&D 5e campaign.
{f'Background: {npc_notes}' if npc_notes else ''}

You are speaking with {char_name}{f' ({char_class})' if char_class else ''}.
Your personal disposition toward {char_name}: {label} (Charisma modifier: {cha_mod:+d}).{org_block}

Stay in character as {npc_name}. Respond naturally to what the character says.
Keep responses concise (2-4 sentences). Do not break character.

After your response, evaluate whether this interaction should shift your affinity toward any party member.
The party members present are: {', '.join(all_chars)}.

Return ONLY valid JSON in this exact format:
{{
  "message": "<your in-character response>",
  "affinity_deltas": [
    {{"char_name": "<name>", "delta": <integer -10 to 10>, "reason": "<brief reason>"}}
  ]
}}

Only include characters in affinity_deltas if the interaction meaningfully affected the relationship.
Most responses should have an empty affinity_deltas array."""


@app.route("/npcs/<int:npc_id>/chat", methods=["POST"])
def npcs_chat(npc_id):
    data = request.json
    cid = data.get("campaign_id") or state.get("campaign_id") or 0
    char_name = (data.get("char_name") or "").strip()
    message = (data.get("message") or "").strip()
    if not char_name or not message:
        return jsonify({"ok": False, "error": "char_name and message required"})

    npc = get_npc(npc_id)
    if not npc:
        return jsonify({"ok": False, "error": "NPC not found"})

    speaking_char = next(
        (c for c in state["game_state"].get("characters", []) if c.get("name", "").lower() == char_name.lower()),
        {"name": char_name}
    )
    affinity = get_npc_affinity(cid, npc_id, char_name)
    org_ctx = compute_interaction_org_score(cid, char_name, npc_id)
    system_prompt = _build_npc_chat_system(npc, speaking_char, affinity, cid, org_ctx)

    try:
        client = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=[types.Content(role="user", parts=[types.Part(text=message)])],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    npc_message = result.get("message", "")
    deltas = result.get("affinity_deltas", [])
    new_affinities = {}
    for d in deltas:
        dname = (d.get("char_name") or "").strip()
        ddelta = int(d.get("delta", 0))
        if dname and ddelta:
            new_score = adjust_npc_affinity(cid, npc_id, dname, ddelta)
            new_affinities[dname] = new_score

    # Include current affinity label for the speaking char
    updated_affinity = get_npc_affinity(cid, npc_id, char_name)
    new_affinities[char_name] = updated_affinity

    return jsonify({
        "ok": True,
        "message": npc_message,
        "affinity_deltas": deltas,
        "new_affinities": {k: {"score": v, "label": _affinity_label(v)} for k, v in new_affinities.items()},
    })


# ── Organizations ────────────────────────────────────────────────────────────────

@app.route("/organizations")
def orgs_list():
    cid = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    return jsonify(list_orgs(cid))


@app.route("/organizations/upsert", methods=["POST"])
def orgs_upsert():
    data = request.json
    cid  = data.get("campaign_id") or state.get("campaign_id") or 0
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"})
    org_id = create_org(
        campaign_id  = cid,
        name         = name,
        org_type     = data.get("org_type", ""),
        description  = data.get("description", ""),
        headquarters = data.get("headquarters", ""),
        notes        = data.get("notes", ""),
    )
    return jsonify({"ok": True, "org_id": org_id})


@app.route("/organizations/<int:org_id>")
def orgs_get(org_id):
    org = get_org(org_id)
    if not org:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(org)


@app.route("/organizations/<int:org_id>/update", methods=["POST"])
def orgs_update(org_id):
    data = request.json
    update_org(org_id,
        name         = data.get("name"),
        org_type     = data.get("org_type"),
        description  = data.get("description"),
        headquarters = data.get("headquarters"),
        notes        = data.get("notes"),
    )
    return jsonify({"ok": True})


@app.route("/organizations/<int:org_id>", methods=["DELETE"])
def orgs_delete(org_id):
    delete_org(org_id)
    return jsonify({"ok": True})


@app.route("/organizations/<int:org_id>/members")
def orgs_members(org_id):
    return jsonify(get_org_members(org_id))


@app.route("/organizations/<int:org_id>/members/add", methods=["POST"])
def orgs_members_add(org_id):
    data = request.json
    cid  = data.get("campaign_id") or state.get("campaign_id") or 0
    entity_type = (data.get("entity_type") or "").strip()
    entity_ref  = (str(data.get("entity_ref") or "")).strip()
    if entity_type not in ("character", "npc") or not entity_ref:
        return jsonify({"ok": False, "error": "entity_type ('character'/'npc') and entity_ref required"})
    add_org_member(org_id, cid, entity_type, entity_ref, data.get("rank", ""))
    return jsonify({"ok": True})


@app.route("/organizations/<int:org_id>/members/remove", methods=["POST"])
def orgs_members_remove(org_id):
    data = request.json
    entity_type = (data.get("entity_type") or "").strip()
    entity_ref  = (str(data.get("entity_ref") or "")).strip()
    if not entity_type or not entity_ref:
        return jsonify({"ok": False, "error": "entity_type and entity_ref required"})
    remove_org_member(org_id, entity_type, entity_ref)
    return jsonify({"ok": True})


@app.route("/organizations/<int:org_id>/affinity")
def orgs_affinity_list(org_id):
    cid = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    return jsonify(get_all_org_affinities(cid, org_id))


@app.route("/organizations/affinity/set", methods=["POST"])
def orgs_affinity_set():
    data = request.json
    cid  = data.get("campaign_id") or state.get("campaign_id") or 0
    a    = data.get("org_id_a")
    b    = data.get("org_id_b")
    score = data.get("score", 0)
    if a is None or b is None:
        return jsonify({"ok": False, "error": "org_id_a and org_id_b required"})
    set_org_affinity(cid, int(a), int(b), int(score))
    return jsonify({"ok": True, "score": max(-100, min(100, int(score)))})


@app.route("/entity/orgs")
def entity_orgs():
    """GET /entity/orgs?type=character&ref=<name>&campaign_id="""
    cid         = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    entity_type = request.args.get("type", "")
    entity_ref  = request.args.get("ref", "")
    if not entity_type or not entity_ref:
        return jsonify([])
    return jsonify(get_entity_orgs(cid, entity_type, entity_ref))


@app.route("/npcs/<int:npc_id>/org-context")
def npcs_org_context(npc_id):
    """Return org-to-org affinity context for a character × NPC interaction."""
    cid       = request.args.get("campaign_id", type=int) or state.get("campaign_id") or 0
    char_name = request.args.get("char_name", "")
    return jsonify(compute_interaction_org_score(cid, char_name, npc_id))


@app.route("/factions/seed-world", methods=["POST"])
def factions_seed_world():
    """Seed well-known Forgotten Realms factions into the current campaign."""
    body = request.json or {}
    cid = body.get("campaign_id") if body.get("campaign_id") is not None else state.get("campaign_id")
    # Last-resort: derive from active session key stored in DB
    if cid is None and state.get("session_key"):
        row = db_load_session(state["session_key"])
        if row:
            cid = row.get("campaign_id")
    if cid is None:
        # Final fallback: use the first campaign in the DB
        campaigns = list_campaigns()
        if campaigns:
            cid = campaigns[0]["id"]
    if cid is None:
        return jsonify({"ok": False, "error": "No active campaign"})
    count = seed_world_factions(cid)
    return jsonify({"ok": True, "seeded": count, "campaign_id": cid})


@app.route("/end-session", methods=["POST"])
def end_session():
    """Final save + clear server state so next page load shows the session picker."""
    save_session()
    state.update({
        "history":         [],
        "turn":            0,
        "session_key":     None,
        "campaign_id":     None,
        "campaign_name":   "",
        "party_context":   "",
        "combat_active":   False,
        "session_mode":    "narrative",
        "combat_ui_state": {},
        "party_loot":      [],
        "game_state": {"gold": 0, "xp": 0, "game_date": "", "location": "", "characters": []},
        "chronicle":       [],
    })
    return jsonify({"ok": True})


@app.route("/save-party-loot", methods=["POST"])
def save_party_loot():
    """Replace the party loot list (full overwrite — client owns the source of truth)."""
    data = request.json or {}
    state["party_loot"] = data.get("party_loot", [])
    save_session()
    return jsonify({"ok": True, "party_loot": state["party_loot"]})


@app.route("/save-combat-state", methods=["POST"])
def save_combat_state():
    """Persist combat_active, session_mode, and full combat UI state from the frontend."""
    data = request.json or {}
    state["combat_active"]   = bool(data.get("combat_active", False))
    state["session_mode"]    = data.get("session_mode", "narrative")
    if "combat_ui" in data:
        state["combat_ui_state"] = data["combat_ui"]
    save_session()
    return jsonify({"ok": True})


# ── Round state ── (per-campaign proxy defined alongside state above) ──────────


# ── Invite / player token routes ────────────────────────────────────────────────

@app.route("/invites", methods=["GET"])
@gm_required
def list_invites():
    cid = state.get("campaign_id")
    if cid is None:
        campaigns = list_campaigns()
        cid = campaigns[0]["id"] if campaigns else 0
    tokens = list_player_tokens(cid)
    return jsonify(tokens)


@app.route("/invites/generate", methods=["POST"])
@gm_required
def generate_invite():
    data = request.json or {}
    char_name = (data.get("character_name") or "").strip()
    # character_name is now optional — blank means the player will set up their own character
    cid = state.get("campaign_id")
    if cid is None:
        campaigns = list_campaigns()
        cid = campaigns[0]["id"] if campaigns else 0
    token = create_player_token(cid, char_name)
    link  = f"{request.host_url}play/{token}"

    # Generate QR code as base64 PNG
    qr_b64 = ""
    try:
        import qrcode, base64
        qr = qrcode.make(link)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass

    return jsonify({"ok": True, "token": token, "link": link, "qr_b64": qr_b64})


@app.route("/invites/<token>/revoke", methods=["POST"])
@gm_required
def revoke_invite(token):
    deactivate_player_token(token)
    return jsonify({"ok": True})


# ── Player-facing routes ────────────────────────────────────────────────────────

@app.route("/play/<token>")
def player_index(token):
    rec = get_player_token(token)
    if not rec:
        return "<h2>Invalid or expired invite link.</h2>", 404
    touch_player_token(token)
    flask_session["player_token"]    = token
    flask_session["player_campaign"] = rec["campaign_id"]

    # No character yet — send player to setup wizard
    if not rec.get("character_name"):
        campaign = get_campaign(rec["campaign_id"]) or {}
        resp = app.make_response(render_template(
            "player_setup.html",
            token=token,
            campaign_name=campaign.get("name", "Adventure"),
        ))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

    flask_session["player_char"] = rec["character_name"]
    resp = app.make_response(render_template(
        "player_session.html",
        character_name=rec["character_name"],
        campaign_id=rec["campaign_id"],
        token=token,
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/play/<token>/setup", methods=["POST"])
def player_setup(token):
    """Called by player_setup.html when the player finishes creating their character."""
    rec = get_player_token(token)
    if not rec:
        return jsonify({"ok": False, "error": "Invalid token"}), 404
    if rec.get("character_name"):
        return jsonify({"ok": False, "error": "Character already set up"}), 400

    data = request.json or {}
    display_name = (data.get("display_name") or "").strip()
    character    = data.get("character") or {}
    char_name    = (character.get("name") or "").strip()

    if not display_name:
        return jsonify({"ok": False, "error": "Display name required"})
    if not char_name:
        return jsonify({"ok": False, "error": "Character name required"})

    campaign_id = rec["campaign_id"]

    # Create player identity
    player_id = create_player(display_name)

    # Create the character
    character["campaign_id"] = campaign_id
    try:
        upsert_character(character, campaign_id)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not save character: {e}"})

    # Seed spellbook from wizard selections
    spell_list   = character.get("spells", [])
    cantrip_names = [s["name"] for s in spell_list if isinstance(s, dict) and s.get("level") == 0]
    spell_names   = [s["name"] for s in spell_list if isinstance(s, dict) and s.get("level", 0) > 0]
    seed_spellbook_from_names(campaign_id, char_name, spell_names, cantrip_names)

    # Link token to player + character
    update_player_token(token, char_name, player_id)
    touch_player(player_id)

    flask_session["player_char"]     = char_name
    flask_session["player_campaign"] = campaign_id

    return jsonify({"ok": True, "character_name": char_name})


@app.route("/player/state")
def player_state():
    """Player polls this to get current session state."""
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    char_name   = flask_session["player_char"]
    campaign_id = flask_session["player_campaign"]

    # Current round submissions visible to all
    submissions = []
    if state.get("session_key") and round_state["round_num"] > 0:
        submissions = get_round_submissions(
            state["session_key"], round_state["round_num"]
        )

    # Character data with effective stats (equipment bonuses applied)
    chars = read_all_characters(campaign_id)
    my_char = next((c for c in chars if c["name"] == char_name), None)
    if my_char:
        eff = _effective_stats(my_char)
        # Overwrite base scores with effective scores so the player sees buffed values
        for s in ('str', 'dex', 'con', 'int', 'wis', 'cha'):
            my_char[s]          = eff[s]
            my_char[s + '_score'] = eff[s]

    # Unread DM count
    unread = 0
    if state.get("session_key"):
        msgs = get_player_messages(state["session_key"], char_name)
        unread = sum(1 for m in msgs if not m["read"] and m["to_character"] == char_name)

    return jsonify({
        "ok":            True,
        "character":     my_char,
        "party_members": [
            {"name": c["name"]}
            for c in (
                state["game_state"].get("characters") or
                read_all_characters(campaign_id, party_only=True)
            )
            if c.get("name") and c["name"] != char_name
        ],
        "session_key":   state.get("session_key"),
        "session_active": bool(state.get("session_key")),
        "game_state":    state["game_state"],
        "round_open":    round_state["open"],
        "round_num":     round_state["round_num"],
        "submissions":   submissions,
        "unread_dms":    unread,
        "map_layout":        state.get("last_map_layout"),
        "scene_description": state.get("last_scene_description"),
        "token_positions":   state.get("last_token_positions", {}),
        "combat_order":      state.get("last_combat_order", []),
        "combat_turn_idx":   state.get("last_combat_turn_idx", 0),
        "combat_round":      state.get("last_combat_round", 1),
        "chronicle":         state["chronicle"][-20:],  # last 20 entries
        "party_chat":        state["party_chat"],
    })


@app.route("/player/submit-action", methods=["POST"])
def player_submit_action():
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    char_name = flask_session["player_char"]
    action    = (request.json or {}).get("action", "").strip()
    if not action:
        return jsonify({"ok": False, "error": "Action cannot be empty"})
    # Queue for GM to pick up via polling
    state["pending_player_actions"].append({
        "character_name": char_name,
        "action_text":    action,
    })
    return jsonify({"ok": True})


@app.route("/player/map")
def player_map():
    """Lightweight map poll — called every 2 s by player session."""
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False}), 401
    return jsonify({
        "ok":               True,
        "map_layout":       state.get("last_map_layout"),
        "scene_description": state.get("last_scene_description"),
        "token_positions":  state.get("last_token_positions", {}),
    })


@app.route("/dm/pending-actions", methods=["GET"])
@gm_required
def dm_pending_actions():
    """Return and clear any queued player turn submissions."""
    actions = state["pending_player_actions"][:]
    state["pending_player_actions"].clear()
    return jsonify({"actions": actions})


@app.route("/player/messages", methods=["GET"])
def player_messages():
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    char_name = flask_session["player_char"]
    if not state.get("session_key"):
        return jsonify({"ok": True, "messages": []})
    msgs = get_player_messages(state["session_key"], char_name)
    mark_messages_read(state["session_key"], char_name)
    return jsonify({"ok": True, "messages": msgs})


@app.route("/player/send-dm", methods=["POST"])
def player_send_dm():
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    char_name = flask_session["player_char"]
    data      = request.json or {}
    to_char   = (data.get("to") or "").strip()
    message   = (data.get("message") or "").strip()
    if not to_char or not message:
        return jsonify({"ok": False, "error": "to and message required"})
    if not state.get("session_key"):
        return jsonify({"ok": False, "error": "No active session"})
    msg_id   = save_player_message(state["session_key"], char_name, to_char, message)
    secret   = bool(data.get("secret", False))
    payload  = {"id": msg_id, "from": char_name, "to": to_char,
                "message": message, "sent_at": datetime.now().isoformat(),
                "secret": secret}
    socketio.emit("direct_message", payload, room=f"player_{to_char}")
    if not secret:
        socketio.emit("dm_spy", payload, room=_gm_room())
    else:
        # GM still gets a redacted notification (knows a secret chat happened, not content)
        socketio.emit("dm_spy_secret", {"from": char_name, "to": to_char}, room=_gm_room())
    return jsonify({"ok": True})


# ── Party chat routes ────────────────────────────────────────────────────────────

@app.route("/party-chat", methods=["GET"])
def party_chat_get():
    """Return recent party chat history. Accessible by authenticated players and GM."""
    is_gm     = flask_session.get("gm_authed")
    is_player = flask_session.get("player_token") and get_player_token(flask_session["player_token"])
    if not is_gm and not is_player:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    return jsonify({"ok": True, "messages": state["party_chat"]})


@app.route("/party-chat", methods=["POST"])
def party_chat_post():
    """Player sends a party chat message."""
    token = flask_session.get("player_token")
    if not token or not get_player_token(token):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    char_name = flask_session["player_char"]
    message   = (request.json or {}).get("message", "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Empty message"})
    _party_chat_broadcast(char_name, message)
    return jsonify({"ok": True})


@app.route("/gm/party-chat", methods=["POST"])
@gm_required
def gm_party_chat_post():
    """GM sends a message into party chat."""
    message = (request.json or {}).get("message", "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Empty message"})
    _party_chat_broadcast("GM", message)
    return jsonify({"ok": True})


def _party_chat_broadcast(from_name: str, message: str):
    entry = {"from": from_name, "message": message,
             "sent_at": datetime.now().isoformat()}
    state["party_chat"].append(entry)
    if len(state["party_chat"]) > PARTY_CHAT_MAX:
        state["party_chat"] = state["party_chat"][-PARTY_CHAT_MAX:]
    socketio.emit("party_chat", entry, room=_session_room())


# ── GM round management routes ──────────────────────────────────────────────────

@app.route("/round/state")
@gm_required
def round_state_get():
    subs = []
    if state.get("session_key") and round_state["round_num"] > 0:
        subs = get_round_submissions(state["session_key"], round_state["round_num"])
    return jsonify({
        "round_open": round_state["open"],
        "round_num":  round_state["round_num"],
        "submissions": subs,
    })


@app.route("/round/open", methods=["POST"])
@gm_required
def round_open():
    if not state.get("session_key"):
        return jsonify({"ok": False, "error": "No active session"})
    round_state["round_num"] += 1
    round_state["open"]       = True
    socketio.emit("round_opened", {
        "round_num":    round_state["round_num"],
        "characters":   [c["name"] for c in state["game_state"]["characters"]],
        "game_date":    state["game_state"].get("game_date", ""),
        "location":     state["game_state"].get("location", ""),
    }, room=_session_room())
    return jsonify({"ok": True, "round_num": round_state["round_num"]})


@app.route("/round/close", methods=["POST"])
@gm_required
def round_close():
    round_state["open"] = False
    socketio.emit("round_closed", {"round_num": round_state["round_num"]},
                  room=_session_room())
    return jsonify({"ok": True})


@app.route("/round/submissions", methods=["GET"])
@gm_required
def round_get_submissions():
    if not state.get("session_key"):
        return jsonify([])
    return jsonify(get_round_submissions(
        state["session_key"], round_state["round_num"]
    ))


@app.route("/round/push", methods=["POST"])
@gm_required
def round_push():
    """GM pushes all player submissions to the AI as a combined turn."""
    if not state.get("session_key"):
        return jsonify({"ok": False, "error": "No active session"})
    subs = get_round_submissions(state["session_key"], round_state["round_num"])
    if not subs:
        return jsonify({"ok": False, "error": "No submissions to push"})

    # Build combined action text
    actions = "\n".join(
        f"{s['character_name']}: {s['action_text']}" for s in subs
    )
    combined = f"[Round {round_state['round_num']} — Party Actions]\n{actions}"
    round_state["open"] = False

    # Inject into the normal chat pipeline
    state["turn"] += 1
    sync_id = generate_sync_id(state["turn"])
    state["history"].append(
        types.Content(role="user", parts=[types.Part(text=f"[sync_id: {sync_id}]\n{combined}")])
    )

    cid              = state.get("campaign_id") or 0
    current_location = state["game_state"].get("location", "")
    location_npcs    = get_npcs_at_location(cid, current_location) if current_location else []

    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model=state["model"],
            contents=state["history"],
            config=types.GenerateContentConfig(
                system_instruction=build_system(
                    state["party_context"], state["session_mode"], "", location_npcs
                ),
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        state["history"].pop()
        state["turn"] -= 1
        return jsonify({"ok": False, "error": str(e)})

    data = parse_dm_response(response.text)
    if not data:
        state["history"].pop()
        state["turn"] -= 1
        return jsonify({"ok": False, "error": "Gemini returned invalid JSON"})

    _log_usage("round_push", response)
    state["history"].append(
        types.Content(role="model", parts=[types.Part(text=response.text)])
    )

    gs = data.get("game_state", {})
    state["game_state"].update({
        "gold":       gs.get("gold",       state["game_state"]["gold"]),
        "xp":         gs.get("xp",         state["game_state"].get("xp", 0)),
        "game_date":  data.get("game_date", state["game_state"]["game_date"]),
        "location":   gs.get("location",   state["game_state"]["location"]),
        "characters": _merge_ai_characters(gs.get("characters"), state["game_state"]["characters"]),
    })
    for _c in state["game_state"]["characters"]:
        if _c.get("name"):
            upsert_character(_c, cid)
    _rebuild_party_context()

    rp_updates      = _apply_rp_notes_updates(data)
    faction_updates = _apply_faction_mentions(data)

    entry = {
        "sync_id":   sync_id,
        "game_date": data.get("game_date", ""),
        "player":    combined,
        "dm":        data.get("dm_response", ""),
    }
    state["chronicle"].append(entry)
    if not state["session_key"]:
        state["session_key"] = _new_session_key()
    save_session()

    narrative = data.get("dm_response", "")
    append_chronicle(
        session_key=state["session_key"], campaign_id=cid, sync_id=sync_id,
        game_date=data.get("game_date", ""), player_text=combined,
        dm_text=narrative, user_raw=combined,
    )

    # Broadcast narrative to all players
    socketio.emit("dm_narrative", {
        "sync_id":    sync_id,
        "narrative":  narrative,
        "game_date":  data.get("game_date", ""),
        "game_state": state["game_state"],
        "round_num":  round_state["round_num"],
    }, room=_session_room())

    # Auto-open next round
    round_state["round_num"] += 1
    round_state["open"]       = True
    socketio.emit("round_opened", {
        "round_num":  round_state["round_num"],
        "characters": [c["name"] for c in state["game_state"]["characters"]],
        "game_date":  data.get("game_date", ""),
        "location":   state["game_state"].get("location", ""),
    }, room=_session_room())

    return jsonify({
        "ok":           True,
        "sync_id":      sync_id,
        "dm_response":  narrative,
        "game_state":   state["game_state"],
        "round_num":    round_state["round_num"],
        "rp_notes_updates": rp_updates,
        "new_factions": faction_updates,
    })


# ── GM DM spy route ─────────────────────────────────────────────────────────────

@app.route("/map/broadcast", methods=["POST"])
@gm_required
def map_broadcast():
    """GM broadcasts current map layout + token positions to all players."""
    data = request.json or {}
    broadcast_map_update(
        map_layout        = data.get("map_layout"),
        scene_description = data.get("scene_description"),
        token_positions   = data.get("token_positions", {}),
    )
    return jsonify({"ok": True})


@app.route("/gm/player-dms")
@gm_required
def gm_player_dms():
    if not state.get("session_key"):
        return jsonify([])
    return jsonify(get_all_player_messages(state["session_key"]))


@app.route("/gm/send-dm", methods=["POST"])
@gm_required
def gm_send_dm():
    data    = request.json or {}
    to_char = (data.get("to") or "").strip()
    message = (data.get("message") or "").strip()
    if not to_char or not message:
        return jsonify({"ok": False, "error": "to and message required"})
    if not state.get("session_key"):
        return jsonify({"ok": False, "error": "No active session"})
    msg_id  = save_player_message(state["session_key"], "GM", to_char, message)
    payload = {"id": msg_id, "from": "GM", "to": to_char,
               "message": message, "sent_at": datetime.now().isoformat(), "secret": False}
    socketio.emit("direct_message", payload, room=f"player_{to_char}")
    return jsonify({"ok": True})


# ── SocketIO events ─────────────────────────────────────────────────────────────

@socketio.on("gm_join")
def on_gm_join(data):
    _thread_cid.id = int(flask_session.get("gm_campaign_id") or 0)
    session_key = data.get("session_key", "nosession")
    join_room(f"session_{session_key}")
    join_room(f"gm_{session_key}")
    emit("joined", {"role": "gm", "session_key": session_key})


@socketio.on("player_join")
def on_player_join(data):
    token = data.get("token", "")
    rec   = get_player_token(token)
    if not rec:
        emit("error", {"message": "Invalid token"})
        return
    _thread_cid.id = int(rec.get("campaign_id") or 0)
    char_name   = rec["character_name"]
    session_key = state.get("session_key", "nosession")
    join_room(f"session_{session_key}")
    join_room(f"player_{char_name}")
    touch_player_token(token)
    emit("joined", {"role": "player", "character_name": char_name,
                    "session_key": session_key})
    # Notify GM
    emit("player_connected", {"character_name": char_name},
         room=f"gm_{session_key}")


@socketio.on("player_disconnect")
def on_player_disconnect():
    _thread_cid.id = int(flask_session.get("player_campaign") or 0)
    char_name = flask_session.get("player_char", "")
    if char_name:
        session_key = state.get("session_key", "nosession")
        emit("player_disconnected", {"character_name": char_name},
             room=f"gm_{session_key}")


# ── Map broadcast helper (call when GM moves tokens) ───────────────────────────

def broadcast_map_update(map_layout=None, scene_description=None, token_positions=None):
    """Broadcast map state to all players. Call from any route that changes the map."""
    if map_layout is not None:
        state["last_map_layout"] = map_layout
    if scene_description is not None:
        state["last_scene_description"] = scene_description
    if token_positions is not None:
        state["last_token_positions"] = token_positions
    socketio.emit("map_update", {
        "map_layout":        state.get("last_map_layout"),
        "scene_description": state.get("last_scene_description"),
        "token_positions":   state.get("last_token_positions", {}),
    }, room=_session_room())


@app.route("/combat/broadcast", methods=["POST"])
@gm_required
def combat_broadcast():
    """GM broadcasts current initiative order + active turn to all players."""
    data = request.json or {}
    state["last_combat_order"]    = data.get("combat_order", [])
    state["last_combat_turn_idx"] = data.get("combat_turn_idx", 0)
    state["last_combat_round"]    = data.get("combat_round", 1)
    socketio.emit("combat_update", {
        "combat_order":    state["last_combat_order"],
        "combat_turn_idx": state["last_combat_turn_idx"],
        "combat_round":    state["last_combat_round"],
    }, room=_session_room())
    return jsonify({"ok": True})


# ── Usage reporting ───────────────────────────────────────────────────────────

@app.route("/gm/usage/sessions", methods=["GET"])
@gm_required
def gm_usage_sessions():
    cid   = request.args.get("campaign_id", None, type=int)
    limit = request.args.get("limit", 100, type=int)
    return jsonify(get_usage_by_session(campaign_id=cid, limit=limit))


@app.route("/gm/usage/by-type", methods=["GET"])
@gm_required
def gm_usage_by_type():
    session_key = request.args.get("session_key", "").strip() or None
    return jsonify(get_usage_by_type(session_key=session_key))


@app.route("/gm/usage/totals", methods=["GET"])
@gm_required
def gm_usage_totals():
    cid = request.args.get("campaign_id", None, type=int)
    return jsonify(get_usage_totals(campaign_id=cid))


# ── Library (Bestiary & Spells Maintenance) ────────────────────────────────────

@app.route("/gm/library")
@gm_required
def gm_library():
    return render_template("library.html")


@app.route("/gm/api/mobs", methods=["GET"])
@gm_required
def gm_api_mobs_list():
    q     = request.args.get("q", "").strip()
    limit = request.args.get("limit", 2000, type=int)
    return jsonify(search_mobs(query=q, limit=limit))


@app.route("/gm/api/mobs/<path:name>", methods=["GET"])
@gm_required
def gm_api_mob_get(name):
    cid = request.args.get("campaign_id", None, type=int)
    mob = get_mob_with_override(name, cid) if cid else get_mob(name)
    if not mob:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(mob)


@app.route("/gm/api/mobs", methods=["POST"])
@gm_required
def gm_api_mob_upsert():
    data = request.json or {}
    if not data.get("name", "").strip():
        return jsonify({"ok": False, "error": "name is required"})
    try:
        upsert_mob(data)
        mob = get_mob(data["name"])
        return jsonify({"ok": True, "mob": mob})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/gm/api/mobs/<path:name>", methods=["DELETE"])
@gm_required
def gm_api_mob_delete(name):
    mob = get_mob(name)
    if not mob:
        return jsonify({"ok": False, "error": "Not found"}), 404
    delete_mob(name)
    return jsonify({"ok": True})


@app.route("/gm/api/spells", methods=["GET"])
@gm_required
def gm_api_spells_list():
    q           = request.args.get("q", "").strip()
    level       = request.args.get("level", None, type=int)
    school      = request.args.get("school", "").strip()
    source      = request.args.get("source", "").strip()
    char_class  = request.args.get("class", "").strip()
    limit       = request.args.get("limit", 100, type=int)
    spells = search_spells_reference(query=q, level=level, school=school,
                                     source=source, char_class=char_class,
                                     enabled_only=False, limit=limit)
    return jsonify(spells)


@app.route("/gm/api/spells/<int:spell_id>", methods=["GET"])
@gm_required
def gm_api_spell_get(spell_id):
    cid   = request.args.get("campaign_id", None, type=int)
    spell = get_spell_with_override(spell_id, cid) if cid else get_spell_reference(spell_id)
    if not spell:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(spell)


@app.route("/gm/api/spells", methods=["POST"])
@gm_required
def gm_api_spell_upsert():
    data = request.json or {}
    if not data.get("name", "").strip():
        return jsonify({"ok": False, "error": "name is required"})
    try:
        spell_id = upsert_spell_reference(data)
        spell    = get_spell_reference(spell_id)
        return jsonify({"ok": True, "spell": spell})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/gm/api/spells/<int:spell_id>", methods=["DELETE"])
@gm_required
def gm_api_spell_delete(spell_id):
    spell = get_spell_reference(spell_id)
    if not spell:
        return jsonify({"ok": False, "error": "Not found"}), 404
    delete_spell_reference(spell_id)
    return jsonify({"ok": True})


@app.route("/gm/api/spell-sources", methods=["GET"])
@gm_required
def gm_api_spell_sources():
    return jsonify(list_spell_sources())


@app.route("/gm/api/mobs/<path:name>/override", methods=["POST"])
@gm_required
def gm_api_mob_override_save(name):
    data = request.json or {}
    cid  = data.get("campaign_id")
    if not cid:
        return jsonify({"ok": False, "error": "campaign_id required"})
    set_mob_override(
        campaign_id = cid,
        mob_name    = name,
        image_path  = data.get("image_path"),
        description = data.get("description"),
        notes       = data.get("notes"),
    )
    return jsonify({"ok": True, "override": get_mob_override(name, cid)})


@app.route("/gm/api/mobs/<path:name>/override", methods=["DELETE"])
@gm_required
def gm_api_mob_override_clear(name):
    cid = request.args.get("campaign_id", type=int)
    if not cid:
        return jsonify({"ok": False, "error": "campaign_id required"})
    clear_mob_override(cid, name)
    return jsonify({"ok": True})


@app.route("/gm/api/spells/<int:spell_id>/override", methods=["POST"])
@gm_required
def gm_api_spell_override_save(spell_id):
    data = request.json or {}
    cid  = data.get("campaign_id")
    if not cid:
        return jsonify({"ok": False, "error": "campaign_id required"})
    enabled = data.get("enabled")
    set_spell_override(
        campaign_id = cid,
        spell_id    = spell_id,
        enabled     = int(enabled) if enabled is not None else None,
        description = data.get("description"),
        notes       = data.get("notes"),
    )
    return jsonify({"ok": True, "override": get_spell_override(spell_id, cid)})


@app.route("/gm/api/spells/<int:spell_id>/override", methods=["DELETE"])
@gm_required
def gm_api_spell_override_clear(spell_id):
    cid = request.args.get("campaign_id", type=int)
    if not cid:
        return jsonify({"ok": False, "error": "campaign_id required"})
    clear_spell_override(cid, spell_id)
    return jsonify({"ok": True})


def _graceful_shutdown(signum, frame):
    """On SIGTERM/SIGINT: flush all active campaign sessions to DB before exiting."""
    log.info("Shutdown signal received — saving active sessions...")
    with _states_lock:
        for cid, s in _states_store.items():
            if s.get("session_key"):
                try:
                    # Temporarily point thread context so save_session() works
                    _thread_cid.id = cid
                    save_session()
                    log.info("Saved session for campaign_id=%s", cid)
                except Exception as e:
                    log.error("Failed to save session for campaign_id=%s: %s", cid, e)
    log.info("Shutdown complete.")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT,  _graceful_shutdown)

# Always run at startup (works under both gunicorn and direct python)
init_db()
threading.Thread(target=_evict_stale_states, daemon=True).start()


def _auto_seed_reference_data():
    """Seed mobs and spells from bundled CSVs if those tables are empty.
    Campaigns and all user data are never touched."""
    import csv as _csv

    base = os.path.dirname(os.path.abspath(__file__))

    # ── Mobs ────────────────────────────────────────────────────────────────
    if count_mobs() == 0:
        mobs_csv = os.path.join(base, "mobs_seed.csv")
        if os.path.exists(mobs_csv):
            log.info("Auto-seeding mobs from %s …", mobs_csv)
            added = skipped = 0

            def _int(v):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return 0

            with open(mobs_csv, newline="", encoding="utf-8") as f:
                for row in _csv.DictReader(f):
                    mob = {
                        "name":          row["name"],
                        "description":   row["description"],
                        "ac":            _int(row["ac"]),
                        "hp_formula":    row["hp_formula"],
                        "hp_avg":        _int(row["hp_avg"]),
                        "speed":         row["speed"],
                        "str":           _int(row["str"]),
                        "dex":           _int(row["dex"]),
                        "con":           _int(row["con"]),
                        "int":           _int(row["int"]),
                        "wis":           _int(row["wis"]),
                        "cha":           _int(row["cha"]),
                        "challenge":     row["challenge"],
                        "xp":            _int(row["xp"]),
                        "size":          row["size"],
                        "mob_type":      row["mob_type"],
                        "alignment":     row["alignment"],
                        "melee_mod":     row["melee_mod"],
                        "ranged_mod":    row["ranged_mod"],
                        "attack1":       row["attack1"],
                        "attack1_range": row["attack1_range"],
                        "attack1_dmg":   row["attack1_dmg"],
                        "attack2":       row["attack2"],
                        "attack2_range": row["attack2_range"],
                        "attack2_dmg":   row["attack2_dmg"],
                        "attack3":       row["attack3"],
                        "attack3_range": row["attack3_range"],
                        "attack3_dmg":   row["attack3_dmg"],
                        "source":        row["source"],
                        "notes":         row["notes"],
                        "languages":     row["languages"],
                    }
                    try:
                        upsert_mob(mob)
                        added += 1
                    except Exception as e:
                        log.warning("Mob seed skipped %s: %s", row.get("name"), e)
                        skipped += 1
            log.info("Mob auto-seed done — %d added, %d skipped.", added, skipped)
        else:
            log.warning("Mobs table is empty but mobs_seed.csv not found at %s", mobs_csv)

    # ── Spells ───────────────────────────────────────────────────────────────
    import sqlite3 as _sqlite3
    from db_manager import DB_PATH as _db_path
    with _sqlite3.connect(_db_path) as _chk:
        _has_cantrips = _chk.execute(
            "SELECT 1 FROM spells_reference WHERE level=0 LIMIT 1"
        ).fetchone()
    if count_spells_reference() == 0 or not _has_cantrips:
        spells_csv = os.path.join(base, "Spells.csv")
        if os.path.exists(spells_csv):
            log.info("Auto-seeding spells from %s …", spells_csv)
            from seed_spells_csv import seed_from_csv as _seed_spells
            _seed_spells(path=spells_csv, default_source="PHB")
            log.info("Spell auto-seed done — %d spells in reference.", count_spells_reference())
        else:
            log.warning("Spells table is empty but Spells.csv not found at %s", spells_csv)

    # ── Mundane items ─────────────────────────────────────────────────────────
    # init_db() seeds only Lifestyle items; check for Weapon category as sentinel
    import sqlite3 as _sqlite3
    from db_manager import DB_PATH as _DB_PATH
    with _sqlite3.connect(_DB_PATH) as _chk:
        _has_weapons = _chk.execute(
            "SELECT 1 FROM mundane_items WHERE category='Weapon' LIMIT 1"
        ).fetchone()
    if not _has_weapons:
        log.info("Auto-seeding mundane items (weapons/armor/gear) …")
        try:
            from seed_mundane_items import ITEMS as _MUNDANE_ITEMS
            for _item in _MUNDANE_ITEMS:
                upsert_mundane_item(_item)
            log.info("Mundane items auto-seed done — %d items total.", count_mundane_items())
        except Exception as _e:
            log.error("Mundane items auto-seed failed: %s", _e)

    # ── Magic items ───────────────────────────────────────────────────────────
    if count_magic_items() == 0:
        log.info("Auto-seeding magic items …")
        try:
            from seed_magic_items import seed as _seed_magic
            _seed_magic()
            log.info("Magic items auto-seed done — %d items total.", count_magic_items())
        except Exception as _e:
            log.error("Magic items auto-seed failed: %s", _e)


_auto_seed_reference_data()

if __name__ == "__main__":
    threading.Timer(1.5, open_in_chrome).start()
    log.info("D&D DM Web App: %s", URL)
    log.info("GM Password: %s", GM_PASSWORD)
    socketio.run(app, port=PORT, debug=False, use_reloader=False)
