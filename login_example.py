"""Example: use LoginClient to login and save tokens to file.

Credentials are read from `login_example_credentials.json` in the project root if present.
The file should contain JSON with keys: base_url, username, password.
If the file is missing or incomplete the script falls back to interactive prompts.
"""

import json
import os
from api.login import LoginClient
from api.komens import KomensClient


def load_credentials(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    cred_path = os.path.join(os.path.dirname(__file__) or ".", "./credentials.json")
    cred_path = os.path.normpath(cred_path)
    creds = load_credentials(cred_path)

    base_url = creds.get("base_url") or input("Base URL (https://...): ")
    username = creds.get("username") or input("Username: ")
    password = creds.get("password") or input("Password: ")

    client = LoginClient(base_url)

    # If credentials were provided, perform login and save tokens. If not, assume tokens already exist.
    if username and password:
        token = client.login_with_password(username, password)
        print("Access token saved to:", client.token_path)
        print("Expires at:", token.expires_at.isoformat())
    else:
        token = client.load_tokens()
        if token:
            print("Using existing tokens from:", client.token_path)
        else:
            print("No credentials or saved tokens available. Exiting.")
            return

    # Fetch and print received komens
    komens = KomensClient(client)
    try:
        data = komens.received()
    except Exception as e:
        print("Failed to fetch komens:", e)
        return

    messages = data.get("Messages") or []
    print(f"Fetched {len(messages)} received messages:\n")
    for m in messages:
        title = m.get("Title")
        sent = m.get("SentDate")
        sender = m.get("Sender", {}).get("Name")
        read = m.get("Read")
        print(f"- [{ 'R' if read else 'U' }] {title} (from: {sender} at {sent}) id={m.get('Id')}")


if __name__ == "__main__":
    main()
