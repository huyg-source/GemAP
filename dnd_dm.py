"""
D&D 5e Dungeon Master Chat
Structured DM session with sync tracking and Google Sheets/Docs integration.
Run this file to start a DnD session.
"""

import sys
import json
import re
import os
from datetime import datetime

os.system("")  # Enable ANSI colour codes on Windows
from google import genai
from google.genai import types
from gemini_chat import get_api_key
from db_manager import init_db, update_from_session, append_session_entry

# ── ANSI colour palette (matches D&D Beyond theme) ─────────────────────────────
R  = "\033[0m"          # reset
RED    = "\033[91m"     # crimson accent
BLUE   = "\033[94m"     # D&D Beyond blue
LBLUE  = "\033[96m"     # light blue (labels)
WHITE  = "\033[97m"     # bright white (body text)
GRAY   = "\033[90m"     # muted / dim
GOLD   = "\033[33m"     # gold / treasure
GREEN  = "\033[92m"     # HP / buffs
DRED   = "\033[91m"     # debuffs / warnings
BOLD   = "\033[1m"

# ── System Prompt ──────────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """
You are a Dungeon Master for Dungeons & Dragons 5th Edition (D&D 5e).
Follow the official D&D 5e rules for all rulings, combat, and mechanics.

RESPONSE FORMAT RULES — these are absolute and must never be broken:
- You MUST respond with a single valid JSON object and nothing else.
- Do NOT include markdown, code fences, backticks, prose, or any text outside the JSON.
- Do NOT add trailing commas. Do NOT add comments inside the JSON.
- All string values must use escaped quotes if they contain quotes.
- "buffs" and "debuffs" must always be JSON arrays — use [] if empty, never null or a string.
- "gold" must always be an integer — use 0 if unknown.
- "hp", "max_hp", and "ac" must always be integers — use 0 if unknown.

STATE PERSISTENCE RULES:
- Carry all values forward from the previous turn unless the current turn changes them.
- If the player's HP, gold, location, buffs or debuffs are unchanged, repeat the last known values.
- If a character has not yet been introduced, do not include them in the characters array.
- If no characters are known yet, use an empty array [].

SYNC ID RULES:
- The user message will begin with [sync_id: XXXX].
- You MUST copy that sync_id value exactly, character for character, into the "sync_id" field.
- Never generate, modify, or omit the sync_id.

JSON STRUCTURE — use exactly this:
{
  "sync_id": "<copied exactly from [sync_id: ...] in the user message>",
  "game_date": "<in-world date, e.g. Day 3, Month of Frost, 1492 DR — advance time naturally>",
  "player_restatement": "<rewrite the player input as clean third-person narrative prose>",
  "dm_response": "<your full DM narrative response to the player>",
  "game_state": {
    "gold": <total gold pieces as integer>,
    "location": "<current location name>",
    "characters": [
      {
        "name": "<character name>",
        "hp": <current hp as integer>,
        "max_hp": <maximum hp as integer>,
        "ac": <armor class as integer>,
        "buffs": ["<active buff name>"],
        "debuffs": ["<active debuff name>"]
      }
    ]
  }
}
"""

# ── Session persistence ────────────────────────────────────────────────────────

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def _history_to_json(history: list) -> list:
    return [
        {"role": c.role, "parts": [{"text": p.text} for p in c.parts]}
        for c in history
    ]


def _history_from_json(data: list) -> list:
    return [
        types.Content(role=item["role"],
                      parts=[types.Part(text=p["text"]) for p in item["parts"]])
        for item in data
    ]


def save_session(history: list, turn: int, session_file: str):
    payload = {
        "last_saved": datetime.now().isoformat(),
        "turn": turn,
        "history": _history_to_json(history),
    }
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_session(session_file: str) -> tuple[list, int]:
    with open(session_file, encoding="utf-8") as f:
        payload = json.load(f)
    return _history_from_json(payload["history"]), payload.get("turn", 0)


def list_sessions() -> list[str]:
    files = sorted(
        [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
        reverse=True
    )
    return [os.path.join(SESSIONS_DIR, f) for f in files]


def pick_session() -> tuple[list, int, str] | tuple[None, int, str]:
    """Prompt user to resume a session or start fresh. Returns (history, turn, session_file)."""
    sessions = list_sessions()
    if not sessions:
        session_file = os.path.join(SESSIONS_DIR, f"session_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        return None, 0, session_file

    print(f"\n{BLUE}{'─'*60}{R}")
    print(f"  {BLUE}{BOLD}SAVED SESSIONS{R}")
    print(f"{BLUE}{'─'*60}{R}")
    for i, path in enumerate(sessions, 1):
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
            saved = meta.get("last_saved", "unknown")[:16].replace("T", " ")
            turns = meta.get("turn", "?")
            name  = os.path.basename(path)
            print(f"  {WHITE}[{i}]{R} {name}")
            print(f"       {GRAY}{turns} turns  |  saved {saved}{R}")
        except Exception:
            print(f"  {WHITE}[{i}]{R} {os.path.basename(path)}  {GRAY}(unreadable){R}")

    print(f"{BLUE}{'─'*60}{R}")
    choice = input(f"  {GRAY}Resume [number] or Enter for new session:{R} ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(sessions):
        path = sessions[int(choice) - 1]
        history, turn = load_session(path)
        print(f"{GREEN}Resuming session — {turn} turns loaded.{R}\n")
        return history, turn, path

    session_file = os.path.join(SESSIONS_DIR, f"session_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    return None, 0, session_file


# ── Helpers ────────────────────────────────────────────────────────────────────

def generate_sync_id(turn: int) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    return f"TURN-{turn:03d}-{ts}"


def parse_response(raw: str) -> dict | None:
    """Extract and parse JSON from Gemini's response."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def display_turn(data: dict):
    """Pretty print the structured DM response for user review."""
    print(f"\n{RED}{'═'*60}{R}")
    print(f"  {GRAY}Sync ID   :{R} {GRAY}{data.get('sync_id', 'N/A')}{R}")
    print(f"  {LBLUE}Game Date :{R} {WHITE}{data.get('game_date', 'N/A')}{R}")
    print(f"{RED}{'═'*60}{R}")

    print(f"\n  {BLUE}{BOLD}WHAT YOU DID:{R}")
    print(f"  {GRAY}{data.get('player_restatement', '')}{R}\n")

    print(f"  {BLUE}{BOLD}DM RESPONSE:{R}")
    print(f"  {WHITE}{data.get('dm_response', '')}{R}\n")

    gs = data.get("game_state", {})
    print(f"{BLUE}{'─'*40}{R}")
    print(f"  {BLUE}{BOLD}GAME STATE{R}")
    print(f"    {LBLUE}Location :{R} {WHITE}{gs.get('location', 'N/A')}{R}")
    print(f"    {GOLD}Gold     :{R} {GOLD}{gs.get('gold', 0)} gp{R}")

    for char in gs.get("characters", []):
        buffs   = ", ".join(char.get("buffs",   [])) or "None"
        debuffs = ", ".join(char.get("debuffs", [])) or "None"
        hp      = char.get('hp', 0)
        max_hp  = char.get('max_hp', 0)
        hp_col  = GREEN if max_hp == 0 or hp / max(max_hp, 1) > 0.5 else DRED
        print(f"\n    {WHITE}{BOLD}{char['name']}{R}")
        print(f"      {LBLUE}HP  :{R} {hp_col}{hp}/{max_hp}{R}  {LBLUE}AC:{R} {WHITE}{char.get('ac')}{R}")
        print(f"      {LBLUE}Buffs   :{R} {GREEN}{buffs}{R}")
        print(f"      {LBLUE}Debuffs :{R} {DRED}{debuffs}{R}")

    print(f"\n{RED}{'═'*60}{R}")


def verify_sync(sent_id: str, received_id: str) -> bool:
    if sent_id != received_id:
        print(f"\n{DRED}[SYNC WARNING]{R} Sent: {sent_id} | Received: {received_id}")
        print(f"  {GRAY}Gemini may have missed the sync_id. Proceed with caution.{R}\n")
        return False
    return True


# ── Main Session ───────────────────────────────────────────────────────────────

def dm_session(model_name: str = "gemini-2.5-flash"):
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    print(f"\n{RED}{'═'*60}{R}")
    print(f"  {RED}{BOLD}D&D 5e DM SESSION{R}  {GRAY}— {model_name}{R}")
    print(f"{RED}{'═'*60}{R}")
    print(f"  {GRAY}Type 'quit' or 'exit' to end. Type 'clear' to reset.{R}")

    loaded, turn, session_file = pick_session()
    history: list[types.Content] = loaded or []

    while True:
        try:
            user_input = input(f"{BLUE}You:{R} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print(f"\n{RED}Farewell, adventurer.{R}\n")
            break
        if user_input.lower() == "clear":
            history = []
            turn = 0
            session_file = os.path.join(SESSIONS_DIR, f"session_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
            print(f"{GRAY}Session cleared — new session started.{R}\n")
            continue

        turn += 1
        sync_id = generate_sync_id(turn)

        # Embed sync_id into the message so Gemini echoes it back
        tagged_input = f"[sync_id: {sync_id}]\n{user_input}"

        history.append(
            types.Content(role="user", parts=[types.Part(text=tagged_input)])
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:
            err = str(e)
            if "429" in err and "free_tier" in err.lower():
                print(f"\n{DRED}[QUOTA EXHAUSTED]{R} Free tier quota used up.")
                print(f"  {GRAY}- Limits reset daily.{R}")
                print(f"  {GRAY}- Enable billing at: https://ai.dev/rate-limit{R}\n")
            else:
                print(f"\n{DRED}API error:{R} {e}\n")
            history.pop()
            turn -= 1
            continue

        raw = response.text
        data = parse_response(raw)

        if not data:
            print(f"\n{DRED}[PARSE ERROR]{R} Gemini did not return valid JSON. Raw response:")
            print(f"{GRAY}{raw}{R}")
            print(f"\n{GRAY}This turn was not saved. Try rephrasing your input.{R}\n")
            history.pop()
            turn -= 1
            continue

        # Verify sync
        verify_sync(sync_id, data.get("sync_id", ""))

        # Display for review
        display_turn(data)

        # Append model reply to history
        history.append(
            types.Content(role="model", parts=[types.Part(text=raw)])
        )

        # Auto-save session to disk
        save_session(history, turn, session_file)

        # Confirm before saving
        try:
            save = input(f"  {BLUE}Save to records?{R} {GRAY}(y/n):{R} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{GRAY}Exiting.{R}")
            break

        if save == "y":
            try:
                append_session_entry(data, user_input)
                update_from_session(data.get("game_state", {}), sync_id, data.get("game_date", ""))
                print(f"{GREEN}[Saved]{R} Doc and Sheet updated.\n")
            except Exception as e:
                print(f"{DRED}[SAVE ERROR]{R} {e}\n")
        else:
            print(f"{GRAY}Not saved.{R}\n")


if __name__ == "__main__":
    init_db()
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.5-flash"
    dm_session(model)
