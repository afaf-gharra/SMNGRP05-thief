"""Commit-reveal over SHA-256 — the reason two strangers can play without a judge.

Each turn a peer seals its true state, move and intent under

    commit = SHA-256( canonical_json(payload) || "|" || nonce )

and transmits *only* the digest. The nonce stays secret until the end of the
match, so at the moment the opponent must act it has absolute certainty that a
decision exists and zero knowledge of what it is. At the final audit every nonce
is revealed and every commit recomputed; a single altered byte changes the digest
completely and the forger takes a technical loss.

Canonical JSON (sorted keys, no incidental whitespace) is what makes this work
across two independently written implementations: both sides must hash
byte-identical input or every honest game would look like fraud.
"""

import hashlib
import json
import secrets
from typing import Any

from p2p_chase.constants import NONCE_BYTES
from p2p_chase.exceptions import CryptoError


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, no ASCII escaping."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(payload: Any) -> str:
    """SHA-256 of a payload's canonical form — used for config and report locks."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class CommitReveal:
    """Seal, recompute and verify per-step commitments."""

    @staticmethod
    def commit_of(payload: dict[str, Any], nonce: str) -> str:
        blob = f"{canonical_json(payload)}|{nonce}".encode()
        return hashlib.sha256(blob).hexdigest()

    @classmethod
    def seal(cls, payload: dict[str, Any]) -> dict[str, str]:
        """Draw a fresh nonce and return ``{"nonce": ..., "commit": ...}``.

        The nonce comes from :mod:`secrets`, not :mod:`random`. The move space is
        tiny — five actions on a 49-cell board — so a predictable nonce would let
        the opponent pre-hash every possibility and read the commitment outright.
        """
        nonce = secrets.token_hex(NONCE_BYTES)
        return {"nonce": nonce, "commit": cls.commit_of(payload, nonce)}

    @classmethod
    def verify(cls, payload: dict[str, Any], nonce: str, commit: str) -> None:
        """Raise :class:`CryptoError` unless ``(payload, nonce)`` hashes to ``commit``."""
        actual = cls.commit_of(payload, nonce)
        if not secrets.compare_digest(actual, commit):
            raise CryptoError(
                f"Commit mismatch: declared {commit[:16]}..., recomputed {actual[:16]}..."
            )


def audit_records(records: list[dict]) -> dict:
    """Re-verify a whole revealed log; both peers run this on the other's records.

    Returns the verdict rather than raising, because the caller needs to *report*
    a failed audit (and score it 0-0) rather than crash on it.
    """
    failed: list[int] = []
    for record in records:
        try:
            CommitReveal.verify(record["payload"], record["nonce"], record["commit"])
        except (CryptoError, KeyError, TypeError):
            step = -1
            if isinstance(record, dict) and isinstance(record.get("payload"), dict):
                step = record["payload"].get("step", -1)
            failed.append(step)
    return {
        "passed": not failed,
        "verified_steps": len(records) - len(failed),
        "total_steps": len(records),
        "failed_steps": failed,
    }
