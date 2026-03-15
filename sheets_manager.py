"""
Sheets Manager
Reads and writes structured DnD game data to the GemDMD Google Sheet.
Tabs: GameState, Initiative, Party
"""

from google_services import get_sheets_client

SHEET_NAME = "GemDMD"

TABS = {
    "game_state": "GameState",
    "initiative": "Initiative",
    "party": "Party",
}


def _get_or_create_tab(sheet, tab_name: str):
    """Return worksheet by name, creating it if it doesn't exist."""
    try:
        return sheet.worksheet(tab_name)
    except Exception:
        return sheet.add_worksheet(title=tab_name, rows=100, cols=20)


def _open_sheet():
    client = get_sheets_client()
    return client.open(SHEET_NAME)


# ── GameState ──────────────────────────────────────────────────────────────────

def update_game_state(location: str, encounter: str, notes: str = ""):
    """Write current game state to the GameState tab."""
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["game_state"])
    ws.clear()
    ws.update("A1", [["Field", "Value"]])
    ws.update("A2", [
        ["Location", location],
        ["Encounter", encounter],
        ["Notes", notes],
    ])
    print(f"[Sheets] GameState updated — {location} / {encounter}")


def read_game_state() -> dict:
    """Read the current game state from the GameState tab."""
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["game_state"])
    rows = ws.get_all_values()
    result = {}
    for row in rows[1:]:  # skip header
        if len(row) >= 2:
            result[row[0]] = row[1]
    return result


# ── Initiative ─────────────────────────────────────────────────────────────────

def update_initiative(combatants: list[dict]):
    """
    Write initiative order to the Initiative tab.
    Each combatant: {"name": str, "initiative": int, "hp": int, "ac": int}
    """
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["initiative"])
    ws.clear()
    ws.update("A1", [["Name", "Initiative", "HP", "AC"]])
    sorted_combatants = sorted(combatants, key=lambda x: x.get("initiative", 0), reverse=True)
    rows = [[c.get("name", ""), c.get("initiative", ""), c.get("hp", ""), c.get("ac", "")] for c in sorted_combatants]
    if rows:
        ws.update("A2", rows)
    print(f"[Sheets] Initiative updated — {len(rows)} combatants")


def read_initiative() -> list[dict]:
    """Read initiative order from the Initiative tab."""
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["initiative"])
    rows = ws.get_all_records()
    return rows


# ── Party ──────────────────────────────────────────────────────────────────────

def update_party(members: list[dict]):
    """
    Write party member data to the Party tab.
    Each member: {"name": str, "class": str, "level": int, "hp": int, "max_hp": int, "ac": int}
    """
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["party"])
    ws.clear()
    ws.update("A1", [["Name", "Class", "Level", "HP", "Max HP", "AC"]])
    rows = [[
        m.get("name", ""),
        m.get("class", ""),
        m.get("level", ""),
        m.get("hp", ""),
        m.get("max_hp", ""),
        m.get("ac", ""),
    ] for m in members]
    if rows:
        ws.update("A2", rows)
    print(f"[Sheets] Party updated — {len(rows)} members")


def read_party() -> list[dict]:
    """Read party data from the Party tab."""
    sheet = _open_sheet()
    ws = _get_or_create_tab(sheet, TABS["party"])
    return ws.get_all_records()


# ── Session Save ───────────────────────────────────────────────────────────────

# Fields written back to Main tab after each session turn (column header → game_state key)
MAIN_TAB_FIELD_MAP = {
    "HP(Current)": "hp",
    "HP(Max)":     "max_hp",
    "AC":          "ac",
    "Buffs":       "buffs",
    "Debuffs":     "debuffs",
    "Status":      "status",
    "Gold":        "gold",
}


def _col_letter(index: int) -> str:
    """Convert 1-based column index to letter (1=A, 2=B ...)."""
    return chr(64 + index)


def _to_list(val) -> list:
    """Split a comma-separated sheet cell into a list, ignoring blanks/None."""
    if not val or str(val).strip().lower() in ("", "none", "-"):
        return []
    return [v.strip() for v in str(val).split(",") if v.strip()]


def _safe_int(val, default=0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def read_main_tab_characters() -> list[dict]:
    """Read all characters from the row-based Main tab."""
    sheet = _open_sheet()
    ws = sheet.worksheet("Main")
    records = ws.get_all_records()  # row 1 = headers, returns list of dicts
    characters = []
    for r in records:
        if not str(r.get("Name", "")).strip():
            continue
        characters.append({
            "name":       str(r.get("Name", "")),
            "group":      str(r.get("Group", "")),
            "race":       str(r.get("Race", "")),
            "class":      str(r.get("Class", "")),
            "subclass":   str(r.get("Subclass", "")),
            "level":      _safe_int(r.get("Level"), 1),
            "profession": str(r.get("Profession", "")),
            "hp":         _safe_int(r.get("HP(Current)")),
            "max_hp":     _safe_int(r.get("HP(Max)")),
            "ki_points":  str(r.get("Ki Points", "")),
            "ac":         _safe_int(r.get("AC")),
            "speed":      str(r.get("Speed", "")),
            "initiative": str(r.get("Initative", "")),
            "status":     str(r.get("Status", "")),
            "gold":       _safe_int(r.get("Gold")),
            "buffs":      _to_list(r.get("Buffs", "")),
            "debuffs":    _to_list(r.get("Debuffs", "")),
            "str":        _safe_int(r.get("STR")),
            "dex":        _safe_int(r.get("DEX")),
            "con":        _safe_int(r.get("CON")),
            "int":        _safe_int(r.get("INT")),
            "wis":        _safe_int(r.get("WIS")),
            "cha":        _safe_int(r.get("CHA")),
            "sending_stone": str(r.get("Sending Stone", "")),
            "items":      _to_list(r.get("ITEMS", "")),
            "notes":      str(r.get("Notes", "")),
        })
    print(f"[Sheets] Main tab read — {len(characters)} characters")
    return characters


def _update_main_tab_characters(sheet, characters: list[dict]):
    """Write session changes back to the row-based Main tab."""
    ws = sheet.worksheet("Main")
    all_values = ws.get_all_values()
    if not all_values:
        return

    header_row = [h.strip() for h in all_values[0]]

    # Name column index (0-based)
    try:
        name_col = header_row.index("Name")
    except ValueError:
        print("[Sheets] Main tab: 'Name' column not found")
        return

    # Build name → sheet row number (1-based, data starts at row 2)
    name_row_map = {}
    for i, row in enumerate(all_values[1:], start=2):
        cell = row[name_col].strip().lower() if len(row) > name_col else ""
        if cell:
            name_row_map[cell] = i

    # Build column header → index map
    col_map = {h: idx for idx, h in enumerate(header_row)}

    updates = []
    for char in characters:
        row_num = name_row_map.get(char.get("name", "").lower().strip())
        if row_num is None:
            print(f"[Sheets] Warning: no row match for '{char.get('name')}'")
            continue
        for field, char_key in MAIN_TAB_FIELD_MAP.items():
            col_idx = col_map.get(field)
            if col_idx is None:
                continue
            value = char.get(char_key, "")
            if isinstance(value, list):
                value = ", ".join(value) if value else ""
            updates.append({"range": f"{_col_letter(col_idx + 1)}{row_num}", "values": [[value]]})

    if updates:
        ws.batch_update(updates)
        print(f"[Sheets] Main tab updated — {len(updates)} cells across {len(characters)} characters")
    else:
        print("[Sheets] Main tab — no matching characters to update")


def update_from_session(game_state: dict, sync_id: str, game_date: str = ""):
    """Update GameState tab and Main character tab from a parsed session."""
    sheet = _open_sheet()

    # GameState tab
    ws = _get_or_create_tab(sheet, TABS["game_state"])
    ws.clear()
    ws.update(range_name="A1", values=[["Field", "Value"]])
    ws.update(range_name="A2", values=[
        ["Sync ID",   sync_id],
        ["Game Date", game_date],
        ["Location",  game_state.get("location", "")],
        ["Gold (gp)", game_state.get("gold", 0)],
        ["XP",        game_state.get("xp", 0)],
    ])
    print(f"[Sheets] GameState updated — sync: {sync_id} | {game_date}")

    # Main tab — character stats
    _update_main_tab_characters(sheet, game_state.get("characters", []))
