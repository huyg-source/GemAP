"""
Docs Manager
Appends narrative session logs and campaign notes to the GemDMT Google Doc.
"""

from datetime import datetime
from google_services import get_docs_client

DOC_ID = "1N-6heeXJQiDocPiI7Yo2DMGBHRxac94dhaQ_6WMRjhE"


def _append_text(text: str):
    """Append text to the end of the Google Doc."""
    client = get_docs_client()

    # Get current end index of the doc
    doc = client.documents().get(documentId=DOC_ID).execute()
    content = doc.get("body", {}).get("content", [])
    end_index = content[-1].get("endIndex", 1) - 1  # -1 to stay before final newline

    requests = [
        {
            "insertText": {
                "location": {"index": end_index},
                "text": text,
            }
        }
    ]
    client.documents().batchUpdate(documentId=DOC_ID, body={"requests": requests}).execute()


def append_session_log(session_text: str):
    """Append a timestamped session log entry to the Doc."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n── SESSION LOG [{timestamp}] ──\n{session_text}\n"
    _append_text(entry)
    print(f"[Docs] Session log appended at {timestamp}")


def append_campaign_note(note_text: str):
    """Append a timestamped campaign note to the Doc."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n── CAMPAIGN NOTE [{timestamp}] ──\n{note_text}\n"
    _append_text(entry)
    print(f"[Docs] Campaign note appended at {timestamp}")


def append_session_entry(data: dict, original_input: str):
    """Append a full structured session turn to the Doc."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    sync_id = data.get("sync_id", "N/A")
    game_date = data.get("game_date", "N/A")
    restatement = data.get("player_restatement", "")
    dm_response = data.get("dm_response", "")

    entry = (
        f"\n\n{'='*60}\n"
        f"Sync ID   : {sync_id}\n"
        f"Real Time : {timestamp}\n"
        f"Game Date : {game_date}\n"
        f"{'='*60}\n"
        f"\nPLAYER:\n{restatement}\n"
        f"\nDM:\n{dm_response}\n"
    )
    _append_text(entry)
    print(f"[Docs] Session entry appended — sync: {sync_id}")
