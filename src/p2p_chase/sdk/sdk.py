"""``ChaseSdk`` — the single entry point for every consumer.

The CLI, the GUI and any third party call this class and nothing deeper
(submission guidelines §4.1). The payoff is concrete rather than architectural
piety: ``play_series`` is the *whole* product, so a new front end is a hundred
lines rather than a reimplementation, and the test suite drives the real
business logic through the same door the operator does.
"""

import json
import logging
from pathlib import Path

from p2p_chase.constants import Role
from p2p_chase.peer.orchestrator import Orchestrator
from p2p_chase.report.emit import emit_series
from p2p_chase.report.naming import result_filename
from p2p_chase.shared.config import ConfigManager
from p2p_chase.shared.terms import describe_scent_model, validate_agreement

logger = logging.getLogger(__name__)


class ChaseSdk:
    """Everything the application can do, behind one object."""

    def __init__(self, config_dir: str | Path, workdir: str | Path = ".") -> None:
        self.config = ConfigManager(config_dir)
        self.workdir = Path(workdir)

    # ------------------------------------------------------------ inspection

    def preflight(self) -> dict:
        """Check we could play right now, without opening a port or sending mail.

        Run by ``p2p-chase doctor`` before a league match, because every problem
        it catches is one that would otherwise surface as a forfeited fixture.
        """
        terms = validate_agreement(self.config)
        return {
            "group_id": self.config.get("game.group_id"),
            "config_dir": str(self.config.dir),
            "agreed_terms": terms,
            "scent_model": describe_scent_model(self.config),
            "my_port": self.config.get("network.my_port"),
            "opponent_url": self.config.get("network.opponent_url"),
            "sub_games": self.config.get("league.num_games"),
            "hint_provider": self.config.get("trash_talk.provider", "template"),
            "email_enabled": bool(self.config.get("email.enabled", False)),
            "email_recipient": self.config.get("email.recipient"),
            "strategy": {
                "police": self.config.get("strategy.police_class"),
                "thief": self.config.get("strategy.thief_class"),
            },
        }

    # ------------------------------------------------------------------ play

    def play_series(
        self, role: str, transport=None, listener=None, send_email: bool = True
    ) -> dict:
        """Play a full series against one opponent, then report it.

        Order matters at the end: the artifacts are written to disk *before* the
        email is attempted, so a mail failure can never cost us the evidence
        that the match happened.
        """
        natural = Role(role)
        validate_agreement(self.config)
        transport = transport or self._build_transport(natural)

        orchestrator = Orchestrator(
            self.config, transport, listener=listener, repo_root=str(self.workdir)
        )
        series = orchestrator.play_series(natural)

        logs_dir = self.workdir / self.config.get("paths.logs_dir", "logs")
        result = emit_series(self.config, logs_dir, series)
        group_id = series.own_identity.get("group_id", "unknown-group")
        result_path = logs_dir / group_id / result_filename(result["game_id"])
        self._settle_series(transport, natural, result, result_path)

        email = self._report(result) if send_email else {"sent": False, "reason": "suppressed"}
        return {
            "result": result,
            "summaries": series.summaries,
            "result_path": str(result_path),
            "artifacts_dir": str(logs_dir / group_id),
            "email": email,
        }

    def _settle_series(self, transport, role: Role, result: dict, path) -> None:
        """Exchange the end-of-series agreement, when the opponent implements it.

        Opt-in on purpose: a peer built on the course reference raises on an
        unknown key in the audit payload, so this must never fire at one. The
        digest is in our report regardless; only the reciprocal exchange is
        conditional.
        """
        if not self.config.get("league.series_consensus", False):
            return
        from p2p_chase.peer.consensus_exchange import exchange

        agreement = result["mutual_agreement"]
        verdict = exchange(transport, role.value, agreement["series_consensus_sha"])
        agreement["peer_consensus_sha"] = verdict["theirs"]
        agreement["series_consensus_agreed"] = verdict["agreed"]
        if note := verdict.get("note"):
            agreement["series_consensus_note"] = note
        # Rewritten rather than patched in memory: the file on disk is the
        # artifact, and the email is built from this same dict a moment later.
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------ artifacts

    def verify_log(self, path: str | Path) -> dict:
        """Re-verify a saved log's commit chain — the replay auditor, headless."""
        from p2p_chase.domain.crypto import audit_records

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        records = data.get("records", data if isinstance(data, list) else [])
        verdict = audit_records(records)
        return {
            "path": str(path),
            "game_id": data.get("game_id"),
            "sub_game_number": data.get("summary", {}).get("sub_game_number"),
            **verdict,
        }

    @staticmethod
    def load_log(path: str | Path) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    # ------------------------------------------------------------- internals

    def _build_transport(self, role: Role):
        from p2p_chase.infra.mcp_client import McpTransport
        from p2p_chase.infra.mcp_server import start_server

        cfg = self.config
        inboxes = start_server(
            role.value, cfg.get("network.host", "0.0.0.0"), cfg.require("network.my_port")
        )
        return McpTransport(
            cfg.require("network.opponent_url"), inboxes,
            connect_timeout=cfg.get("network.connect_timeout_seconds", 60),
            retry_interval=cfg.get("network.retry_interval_seconds", 1.0),
            audit_timeout=cfg.get("network.audit_send_timeout_seconds", 10),
            opponent_urls=cfg.get("network.opponent_urls", {}),
        )

    def _report(self, result: dict) -> dict:
        from p2p_chase.infra.gmail_sender import GmailReporter
        from p2p_chase.shared.gatekeeper import ApiGatekeeper

        reporter = GmailReporter(
            self.config, ApiGatekeeper(self.config.service_limits("gmail"), service="gmail")
        )
        return reporter.send_result(result, result_filename(result["game_id"]))
