"""
Gemini Interactive Chat Session Reader
Connects to the Google Gemini API, runs an interactive chat loop,
and parses/extracts key fields from each response.
"""

import os
import sys
from google import genai
from google.genai import types


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it before starting the server."
        )
    return key


def display_response(response, turn: int):
    print(f"\n{'='*60}")
    print(f"  Turn {turn} — Gemini Response")
    print(f"{'='*60}")

    # Extract and print text
    text = response.text
    print(f"\n{text}")

    # Parse metadata / usage stats
    print(f"\n{'─'*40}")
    print("  Metadata:")

    if response.usage_metadata:
        um = response.usage_metadata
        print(f"    Prompt tokens   : {um.prompt_token_count}")
        print(f"    Response tokens : {um.candidates_token_count}")
        print(f"    Total tokens    : {um.total_token_count}")

    # Model / finish reason from candidates
    if response.candidates:
        candidate = response.candidates[0]
        finish = candidate.finish_reason
        print(f"    Finish reason   : {finish}")

        if candidate.safety_ratings:
            print("    Safety ratings  :")
            for rating in candidate.safety_ratings:
                print(f"      {rating.category}: {rating.probability}")

    print(f"{'='*60}\n")


DEFAULT_SYSTEM_INSTRUCTION = "You are a helpful assistant. Be concise and clear."


def chat_session(model_name: str = "gemini-2.5-flash", system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION):
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    print(f"\nGemini Chat Session — model: {model_name}")
    print("Type 'quit' or 'exit' to end. Type 'clear' to start a new session.\n")

    history: list[types.Content] = []
    turn = 0

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye.")
            break

        if user_input.lower() == "clear":
            history = []
            turn = 0
            print("Session cleared.\n")
            continue

        # Append user turn to history
        history.append(
            types.Content(role="user", parts=[types.Part(text=user_input)])
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                ),
            )
        except Exception as e:
            err = str(e)
            if "429" in err and "free_tier" in err.lower():
                print("\n[QUOTA EXHAUSTED] You have used up your free tier quota for the Gemini API.")
                print("  - Free tier limits reset daily.")
                print("  - To continue now, enable billing at: https://ai.dev/rate-limit")
                print("  - Or wait until your quota resets tomorrow.\n")
            else:
                print(f"\nAPI error: {e}\n")
            # Remove the failed user turn so history stays consistent
            history.pop()
            continue

        turn += 1
        display_response(response, turn)

        # Append model reply to history for multi-turn context
        reply_text = response.text
        history.append(
            types.Content(role="model", parts=[types.Part(text=reply_text)])
        )


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.5-flash"
    chat_session(model_name=model)
