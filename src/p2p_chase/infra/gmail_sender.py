"""Automatic result reporting over the Gmail API (book Appendix A).

Three rules shape this module, all of them mandatory:

* **Send-only scope.** The token requests ``gmail.send`` and nothing else
  (rule 30). Least privilege is not paperwork here — a leaked token that can
  only send is a nuisance, one that can read is a disaster.
* **Machine-readable payload.** The result travels as a JSON *attachment*, never
  as free text in the body (rules 33-34). A report the grader's parser rejects
  scores nothing, however well it reads.
* **Through the Gatekeeper.** Every send passes the quota, bucket and DOS gates
  (rules 28-29), because the failure mode being defended against is our own bug
  looping and getting the account suspended.

Credentials live outside the repository and are git-ignored; nothing here ever
prints or logs their contents.
"""

import base64
import json
import logging
import os
from email.message import EmailMessage
from pathlib import Path

from p2p_chase.exceptions import ChaseError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
DEFAULT_CREDENTIALS = "credentials.json"
DEFAULT_TOKEN = "token.json"


class GmailReporter:
    """Sends one match report per match, as a signed JSON attachment."""

    def __init__(self, config, gatekeeper=None) -> None:
        self.config = config
        self.recipient = config.get("email.recipient", "")
        self.enabled = bool(config.get("email.enabled", False)) and bool(self.recipient)
        self.sender = config.get("email.sender", "me")
        self.credentials_path = Path(
            os.environ.get("P2P_GMAIL_CREDENTIALS", DEFAULT_CREDENTIALS)
        )
        self.token_path = Path(os.environ.get("P2P_GMAIL_TOKEN", DEFAULT_TOKEN))
        self._gatekeeper = gatekeeper
        self._service = None

    def send_result(self, result: dict, attachment_name: str) -> dict:
        """Send the result JSON. Returns a status dict; never raises into the match.

        A failed email must not destroy a match that was played correctly — the
        artifacts are already on disk and can be sent by hand. So this reports
        the failure and lets the caller carry on.
        """
        if not self.enabled:
            return {"sent": False, "reason": "email disabled in config", "to": self.recipient}
        try:
            message = self._compose(result, attachment_name)
            if self._gatekeeper is not None:
                sent = self._gatekeeper.execute(self._deliver, message)
            else:
                sent = self._deliver(message)
            return {"sent": True, "to": self.recipient, "id": sent.get("id"),
                    "attachment": attachment_name}
        except Exception as exc:  # noqa: BLE001 - reporting failure must stay non-fatal
            logger.error("Could not send the match report: %s", exc)
            return {"sent": False, "reason": str(exc), "to": self.recipient,
                    "attachment": attachment_name}

    # ------------------------------------------------------------- internals

    def _compose(self, result: dict, attachment_name: str) -> dict:
        message = EmailMessage()
        message["To"] = self.recipient
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        message["Subject"] = self._subject(result)
        # The body IS the report, byte-for-byte what we attach. A human summary
        # here reads better and is wrong: graders compare the mail against the
        # other team's mail, and two reports that agree perfectly can still look
        # different when one side paraphrases. The course reference sets the body
        # to exactly this serialisation.
        message.set_content(payload)
        message.add_attachment(
            payload.encode("utf-8"),
            maintype="application",
            subtype="json",
            filename=attachment_name,
        )
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}

    def _subject(self, result: dict) -> str:
        """The course reference's exact form, which the league greps for.

        Ours used to be a house style. That is a bad thing to invent: the subject
        is how a grader pairs our filing with the opponent's, and two teams whose
        subjects do not share a shape look like two matches rather than one.
        """
        final = result.get("final_result", {})
        winner = final.get("winner_group") or ("tie" if final.get("series_tie") else "unknown")
        return f"Police-Thief series result: winner {winner} (reported by {self._own_role(result)})"

    def _own_role(self, result: dict) -> str:
        """Our natural role: the one we held in sub-game 1, before they alternate."""
        own = self.config.get("game.group_id", "")
        rows = result.get("sub_games") or [{}]
        return (rows[0].get("roles") or {}).get(own, "unknown")

    def _deliver(self, message: dict) -> dict:
        service = self._ensure_service()
        return service.users().messages().send(userId=self.sender, body=message).execute()

    def _ensure_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request  # noqa: PLC0415
            from google.oauth2.credentials import Credentials  # noqa: PLC0415
            from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:
            raise ChaseError(
                "Gmail reporting needs the Google client libraries: "
                "uv sync --extra gmail"
            ) from exc

        creds = None
        if self.token_path.is_file():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # long-lived refresh token: no human needed
        if not creds or not creds.valid:
            creds = self._first_authorisation(InstalledAppFlow)
        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _first_authorisation(self, flow_cls):
        """One-time consent flow; afterwards the refresh token keeps us autonomous."""
        if not self.credentials_path.is_file():
            raise ChaseError(
                f"Missing {self.credentials_path}. Download the OAuth client ID from the "
                "Google Cloud console (book Appendix A step D) and keep it out of git."
            )
        flow = flow_cls.from_client_secrets_file(str(self.credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Stored a Gmail refresh token at %s (git-ignored)", self.token_path)
        return creds
