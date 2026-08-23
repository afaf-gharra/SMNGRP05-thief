"""Re-mint ``token.json`` when Gmail refuses the refresh.

A live series settled cleanly and then could not file, because the stored
refresh token came back ``invalid_grant: Token has been expired or revoked``.
The cause is almost always the OAuth consent screen still being in **Testing**
publishing status, where Google expires refresh tokens after seven days
regardless of use. Ours was minted on 15/08 and died on the 22nd.

This is the one operation the agent cannot perform for itself: it opens a
browser and needs a human to approve the scope. Run it, click through, and both
repositories get a fresh token.

    uv run python scripts/mint_gmail_token.py

Scope is ``gmail.send`` and nothing else (rule 30). A leaked send-only token is
a nuisance; one that can read is a disaster.
"""

import shutil
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
ROOT = Path(__file__).resolve().parents[1]
SIBLING = ROOT.parent / ("SMNGRP05-police" if ROOT.name.endswith("thief") else "SMNGRP05-thief")


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415

    credentials = ROOT / "credentials.json"
    if not credentials.exists():
        print(f"No {credentials} — download it from the Google Cloud console first.")
        return 1

    print("A browser window will open. Approve the 'send email' scope.\n")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials), SCOPES)
    creds = flow.run_local_server(port=0)

    target = ROOT / "token.json"
    target.write_text(creds.to_json(), encoding="utf-8")
    print(f"wrote {target}")

    # Both peers send from the same account, so the sibling repository gets the
    # same token rather than a second consent round.
    if SIBLING.exists():
        shutil.copy2(target, SIBLING / "token.json")
        print(f"wrote {SIBLING / 'token.json'}")

    print("\nDone. Verify with a real send before the next match rather than after it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
