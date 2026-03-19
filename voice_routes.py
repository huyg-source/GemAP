"""
voice_routes.py — Daily.co voice chat integration.

Routes:
  POST /voice/start   — GM creates a voice room for the current session
  GET  /voice/token   — player gets a participant token for the active room
  POST /voice/end     — GM closes the voice room

Env vars required:
  DAILY_API_KEY — from daily.co dashboard (Settings → Developers)
"""

import os
import re
import logging

try:
    import requests
except ImportError:
    requests = None
from flask import Blueprint, jsonify, request
from flask_login import current_user

log = logging.getLogger("dnd.voice")

DAILY_API_KEY = os.environ.get("DAILY_API_KEY", "")
DAILY_BASE    = "https://api.daily.co/v1"

voice_bp = Blueprint("voice_bp", __name__, url_prefix="/voice")


def _headers():
    return {"Authorization": f"Bearer {DAILY_API_KEY}", "Content-Type": "application/json"}


def _safe_room_name(session_key: str) -> str:
    """Daily room names: max 40 chars, alphanumeric + hyphens."""
    slug = re.sub(r"[^a-z0-9]", "-", session_key.lower())[:40].strip("-")
    return slug or "dnd-session"


# ── GM: create room ───────────────────────────────────────────────────────────

@voice_bp.route("/start", methods=["POST"])
def voice_start():
    """GM calls this when they want to open voice for the session."""
    from dm_web import state, flask_session

    if not flask_session.get("gm_logged_in") and not (
        current_user.is_authenticated and current_user.is_pro()
    ):
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    if not DAILY_API_KEY:
        return jsonify({"ok": False, "error": "DAILY_API_KEY not configured"}), 500
    if not requests:
        return jsonify({"ok": False, "error": "requests library not available"}), 500

    session_key = state.get("session_key")
    if not session_key:
        return jsonify({"ok": False, "error": "No active session"}), 400

    room_name = _safe_room_name(session_key)

    # Create room (idempotent — Daily returns existing room if name matches)
    resp = requests.post(
        f"{DAILY_BASE}/rooms",
        headers=_headers(),
        json={
            "name":       room_name,
            "privacy":    "private",          # token required to join
            "properties": {
                "exp":              4 * 3600, # expires after 4 hours
                "eject_at_room_exp": True,
                "enable_chat":      False,    # we have our own chat
                "start_video_off":  True,     # audio only by default
            },
        },
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        log.error("Daily room create failed: %s", resp.text)
        return jsonify({"ok": False, "error": "Failed to create voice room"}), 500

    room = resp.json()
    state["voice_room"] = room_name

    # Mint a GM owner token
    tok_resp = requests.post(
        f"{DAILY_BASE}/meeting-tokens",
        headers=_headers(),
        json={
            "properties": {
                "room_name":   room_name,
                "is_owner":    True,
                "user_name":   "Dungeon Master",
                "enable_recording": False,
            }
        },
        timeout=10,
    )
    if tok_resp.status_code != 200:
        log.error("Daily GM token failed: %s", tok_resp.text)
        return jsonify({"ok": False, "error": "Failed to mint GM token"}), 500

    return jsonify({
        "ok":       True,
        "room_url": room["url"],
        "token":    tok_resp.json()["token"],
        "room_name": room_name,
    })


# ── Player: get participant token ─────────────────────────────────────────────

@voice_bp.route("/token", methods=["GET"])
def voice_token():
    """Player calls this to get a token for the active voice room."""
    from dm_web import state, flask_session

    if not flask_session.get("player_token"):
        return jsonify({"ok": False, "error": "Not authenticated"}), 401

    if not DAILY_API_KEY or not requests:
        return jsonify({"ok": False, "error": "Voice not configured"}), 500

    room_name = state.get("voice_room")
    if not room_name:
        return jsonify({"ok": False, "room_name": None})  # voice not started yet

    char_name = flask_session.get("player_char", "Adventurer")

    tok_resp = requests.post(
        f"{DAILY_BASE}/meeting-tokens",
        headers=_headers(),
        json={
            "properties": {
                "room_name": room_name,
                "is_owner":  False,
                "user_name": char_name,
            }
        },
        timeout=10,
    )
    if tok_resp.status_code != 200:
        log.error("Daily player token failed: %s", tok_resp.text)
        return jsonify({"ok": False, "error": "Failed to mint token"}), 500

    room_resp = requests.get(
        f"{DAILY_BASE}/rooms/{room_name}",
        headers=_headers(),
        timeout=10,
    )
    room_url = room_resp.json().get("url", "") if room_resp.status_code == 200 else ""

    return jsonify({
        "ok":       True,
        "room_url": room_url,
        "token":    tok_resp.json()["token"],
        "room_name": room_name,
    })


# ── GM: end room ──────────────────────────────────────────────────────────────

@voice_bp.route("/end", methods=["POST"])
def voice_end():
    """GM closes the voice room — called on session end or manually."""
    from dm_web import state, flask_session

    if not flask_session.get("gm_logged_in") and not (
        current_user.is_authenticated and current_user.is_pro()
    ):
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    room_name = state.get("voice_room")
    if not room_name:
        return jsonify({"ok": True})  # nothing to close

    if DAILY_API_KEY:
        requests.delete(
            f"{DAILY_BASE}/rooms/{room_name}",
            headers=_headers(),
            timeout=10,
        )

    state["voice_room"] = None
    return jsonify({"ok": True})
