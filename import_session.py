"""
Session Importer
Reads a raw Gemini DM conversation from the clipboard, formats it
into a sessions/*.json file the DM app can resume from.
Run: python import_session.py
"""

import json
import os
import sys
import tkinter as tk
from datetime import datetime
from google import genai
from google.genai import types
from gemini_chat import get_api_key

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

PROMPT = """You are a data formatter. I will give you a raw D&D DM conversation transcript.
Convert it into a JSON object in exactly this format — output ONLY valid JSON, nothing else:

{{
  "last_saved": "{today}",
  "turn": <total number of complete user/model turn pairs as integer>,
  "history": [
    {{"role": "user",  "parts": [{{"text": "<user message text>"}}]}},
    {{"role": "model", "parts": [{{"text": "<model response text>"}}]}},
    ... one entry per message, alternating user then model, in chronological order ...
  ]
}}

Rules:
- Every player/user message becomes a "role":"user" entry.
- Every DM/AI response becomes a "role":"model" entry.
- Preserve the full text of each message exactly as written.
- "turn" = total number of user messages.
- Output ONLY the JSON object. No explanation, no markdown, no code fences.

Conversation transcript:

{transcript}"""


def get_clipboard() -> str:
    root = tk.Tk()
    root.withdraw()
    try:
        text = root.clipboard_get()
    except tk.TclError:
        text = ""
    root.destroy()
    return text


def main():
    print("\n=== DM Session Importer ===")
    print("Reading from clipboard...")

    transcript = get_clipboard().strip()
    if not transcript:
        print("Clipboard is empty. Copy your conversation first then run this again.")
        sys.exit(1)

    preview = transcript[:200].replace("\n", " ")
    print(f"Found {len(transcript)} characters. Preview: {preview}...")
    confirm = input("\nLook right? (y/n): ").strip().lower()
    if confirm != "y":
        print("Aborted. Copy the conversation and try again.")
        sys.exit(0)

    print("\nSending to Gemini for formatting...")

    client = genai.Client(api_key=get_api_key())
    prompt = PROMPT.format(today=datetime.now().isoformat(), transcript=transcript)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        print(f"API error: {e}")
        sys.exit(1)

    try:
        data = json.loads(response.text.strip())
    except json.JSONDecodeError as e:
        print(f"Failed to parse response as JSON: {e}")
        print("Raw response:")
        print(response.text)
        sys.exit(1)

    if "history" not in data or not isinstance(data["history"], list):
        print("Response is missing 'history'. Raw:")
        print(response.text)
        sys.exit(1)

    turns = data.get("turn", len([e for e in data["history"] if e.get("role") == "user"]))
    print(f"Formatted {turns} turns successfully.")

    name = input("\nSave as (leave blank for auto-name): ").strip()
    if not name:
        name = f"session_imported_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if not name.endswith(".json"):
        name += ".json"

    out_path = os.path.join(SESSIONS_DIR, name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to: {out_path}")
    print("Start dnd_dm.py and select this session from the resume list.")


if __name__ == "__main__":
    main()
