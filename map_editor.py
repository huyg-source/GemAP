"""
D&D Map Editor — Flask server
Serves the browser-based grid map editor and handles save/load.
Run with: python map_editor.py
Opens automatically at http://localhost:5000 in Chrome.
"""

import os
import re
import threading
import subprocess
from flask import Flask, render_template, request, jsonify
from google import genai
from google.genai import types
from gemini_chat import get_api_key
from db_manager import init_db, save_map, load_map, list_maps, delete_map

app = Flask(__name__)

URL = "http://localhost:5000"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome():
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def open_in_chrome():
    chrome = find_chrome()
    if chrome:
        # --new-window keeps it as its own window, easy to tag in Gemini
        subprocess.Popen([chrome, f"--new-window", URL])
    else:
        # Fall back to system default browser
        import webbrowser
        webbrowser.open(URL)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    resp = app.make_response(render_template("map_editor.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/save", methods=["POST"])
def save():
    data = request.json
    name = data.get("name", "untitled").strip().replace(" ", "_")
    description = data.get("description", "")
    save_map(name, description, data)
    return jsonify({"ok": True, "name": name})


@app.route("/load/<name>")
def load(name):
    row = load_map(name)
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row["data"])


@app.route("/maps")
def get_maps():
    return jsonify(list_maps())


@app.route("/delete-map", methods=["POST"])
def delete_map_route():
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "No name provided"})
    delete_map(name)
    return jsonify({"ok": True})


# ── Entry point ────────────────────────────────────────────────────────────────

@app.route("/gemini-room", methods=["POST"])
def gemini_room():
    data        = request.json
    description = data.get("description", "")
    scale       = int(data.get("scale", 5))
    start_col   = int(data.get("start_col", 0))
    start_row   = int(data.get("start_row", 0))

    system = f"""You are a D&D dungeon map assistant converting room descriptions into grid drawing commands.

SCALE: {scale} feet per grid square.
ROOM ORIGIN: top-left corner at grid position (col={start_col}, row={start_row}).

COORDINATE SYSTEM:
- Rows increase downward. Cols increase rightward.
- Cell (row=R, col=C) occupies the square from grid point (R,C) to (R+1,C+1).

EDGE RULES:
- Horizontal edge "h" at (row=R, col=C) = the TOP border of cell (R,C).
  - Top wall of an N-tall, M-wide room: h edges at (start_row, start_col) through (start_row, start_col+M-1).
  - Bottom wall: h edges at row start_row+N.
- Vertical edge "v" at (row=R, col=C) = the LEFT border of cell (R,C).
  - Left wall: v edges at (start_row, start_col) through (start_row+N-1, start_col).
  - Right wall: v edges at col start_col+M.

EXAMPLE — 10x10 ft room (2x2 squares) at col=3, row=2 with scale=5:
  Top:    h(2,3) h(2,4)
  Bottom: h(4,3) h(4,4)
  Left:   v(2,3) v(3,3)
  Right:  v(2,5) v(3,5)
  Floor cells: (2,3),(2,4),(3,3),(3,4) color #f5f0e8

DIMENSION CONVENTION — always strictly follow this:
- "WxH" means WIDTH x HEIGHT. Width = columns (left-right). Height = rows (top-down).
- Example: "30x50 room" at scale=5 → 6 columns wide, 10 rows tall. NEVER swap these.
- The first number is ALWAYS width (columns). The second is ALWAYS height (rows).

Convert feet to squares by dividing by {scale} (round to nearest whole square).
Place doors and windows as single edges replacing a wall segment.
Add floor cells for the interior. Add colored cells for features (fireplace=red, water=blue, stairs-up=green, stairs-down=darkred, magic=purple).

Return ONLY valid JSON, no other text:
{{
  "edges": [{{"type": "h", "row": 0, "col": 0, "tool": "wall"}}],
  "cells": [{{"row": 0, "col": 0, "color": "#f5f0e8", "label": ""}}],
  "summary": "what was drawn"
}}

Tool options for edges: "wall", "door", "window"
Cell colors: "#f5f0e8" floor, "#4a90d9" water, "#2ecc71" stairs-up, "#c0392b" stairs-down, "#9b59b6" magic, "#b0a898" stone, "#e8832a" fireplace"""

    try:
        client   = genai.Client(api_key=get_api_key())
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=description)])],
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
            ),
        )
        raw     = re.sub(r"```(?:json)?", "", response.text).replace("```", "").strip()
        result  = json.loads(raw)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    threading.Timer(1.5, open_in_chrome).start()
    print(f"D&D Map Editor: {URL}")
    app.run(port=5000, debug=False, use_reloader=False)
