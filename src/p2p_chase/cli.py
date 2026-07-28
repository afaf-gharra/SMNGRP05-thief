"""Command line interface. Zero business logic — everything delegates to the SDK.

Two terminals, two peers, no central server::

    uv run python -m p2p_chase peer --role police
    uv run python -m p2p_chase peer --role thief

and afterwards::

    uv run python -m p2p_chase replay --log logs/<group>/log_<game_id>_g01.json
    uv run python -m p2p_chase verify --log logs/<group>/log_<game_id>_g01.json
    uv run python -m p2p_chase doctor --role police
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from p2p_chase.exceptions import ChaseError
from p2p_chase.sdk.sdk import ChaseSdk


def default_config(role: str) -> str:
    """Each peer has its own config directory — two students, two machines."""
    return str(Path("config") / role)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p2p-chase",
        description="Distributed cops-and-robbers between two autonomous MCP agents.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command")

    peer = sub.add_parser("peer", help="run one autonomous agent")
    peer.add_argument("--role", required=True, choices=["police", "thief"],
                      help="this peer's natural role; roles alternate across sub-games")
    peer.add_argument("--config", default=None, help="config directory (default: config/<role>)")
    peer.add_argument("--no-gui", action="store_true", help="headless: console only")
    peer.add_argument("--no-email", action="store_true", help="write artifacts but do not send")

    replay = sub.add_parser("replay", help="replay a saved log with cryptographic verification")
    replay.add_argument("--log", required=True)
    replay.add_argument("--config", default=default_config("police"))

    verify = sub.add_parser("verify", help="verify a saved log's commit chain, headless")
    verify.add_argument("--log", required=True)
    verify.add_argument("--config", default=default_config("police"))

    doctor = sub.add_parser("doctor", help="pre-match readiness check")
    doctor.add_argument("--role", default="police", choices=["police", "thief"])
    doctor.add_argument("--config", default=None)
    return parser


def run_peer(args) -> int:
    sdk = ChaseSdk(args.config or default_config(args.role))
    if args.no_gui:
        outcome = sdk.play_series(args.role, send_email=not args.no_email)
    else:  # pragma: no cover - Tkinter
        from p2p_chase.gui.live_app import LivePeerApp

        outcome = LivePeerApp(sdk, args.role, send_email=not args.no_email).run()
    print(json.dumps(_headline(outcome), ensure_ascii=False, indent=2))
    return 0


def _headline(outcome: dict) -> dict:
    final = outcome["result"]["final_result"]
    return {
        "game_id": outcome["result"]["game_id"],
        "sub_games": outcome["result"]["num_sub_games"],
        "total_score": final.get("total_score"),
        "winner_group": final.get("winner_group"),
        "series_tie": final.get("series_tie"),
        "artifacts": outcome["artifacts_dir"],
        "email": outcome["email"],
    }


def run_replay(args) -> int:  # pragma: no cover - Tkinter
    from p2p_chase.gui.replay_app import ReplayApp

    sdk = ChaseSdk(args.config)
    ReplayApp(sdk.config, sdk.load_log(args.log), log_path=args.log).run()
    return 0


def run_verify(args) -> int:
    sdk = ChaseSdk(args.config)
    verdict = sdk.verify_log(args.log)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    stamp = "Verified OK" if verdict["passed"] else "TAMPERED"
    print(f"\n{stamp}: {verdict['verified_steps']}/{verdict['total_steps']} steps verified")
    return 0 if verdict["passed"] else 1


def run_doctor(args) -> int:
    sdk = ChaseSdk(args.config or default_config(args.role))
    print(json.dumps(sdk.preflight(), ensure_ascii=False, indent=2))
    return 0


COMMANDS = {
    "peer": run_peer, "replay": run_replay, "verify": run_verify, "doctor": run_doctor,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args)
    except ChaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - operator action
        print("\nInterrupted.", file=sys.stderr)
        return 130
