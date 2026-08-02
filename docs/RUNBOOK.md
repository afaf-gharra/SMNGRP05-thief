# Match-day runbook

Follow this in order for every fixture. Most of it is agreeing things with the
opponent *before* anyone starts a process — that is where matches are actually
lost, not in the code.

---

## A. Agree with the opponent, in writing, before match day

### A1. Who launches which role — **the one that silently ruins a series**

Roles alternate by sub-game index, and both peers apply the *same* rule. So if
both teams launch with `--role police`, both are the officer in sub-game 1 and
the series is nonsense.

| | sub-game 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Team launching `--role police` | police | thief | police | thief | police | thief |
| Team launching `--role thief` | thief | police | thief | police | thief | police |

**Agree explicitly: one team launches `police`, the other launches `thief`.**
Nothing in the protocol detects this mistake — the match will simply be wrong.

### A2. The shared game.json must match byte for byte

Send them `config/police/game.json` and ask them to use it **verbatim**. The
handshake refuses to play on any difference and names the offending key, so this
fails safely — but it fails, and a fixture is wasted.

Two fields differ from the course reference simulator's shipped defaults, so
call them out explicitly:

| Term | Must be | Reference ships |
|---|---|---|
| `num_games` | **6** (Appendix F) | `1` |
| `world.map_area` | **"New York"** | sometimes `""` |

Everything else in our file already matches the reference exactly.

### A3. Exchange tunnel URLs

Each side sends the other its public MCP URL, ending in `/mcp`.

---

## B. Thirty minutes before

**1. Start the tunnel**

```bash
ngrok http 8801
```

Copy the `https://….ngrok-free.app` address it prints.

**2. Put their URL in your private config** — `config/thief/game.toml`:

```toml
[network]
opponent_url = "https://THEIR-TUNNEL.ngrok-free.app/mcp"
```

and put *your* tunnel URL in `game.mcp_servers` so it reaches the declaration.

**3. Pre-flight check**

```bash
uv run python -m p2p_chase doctor --role thief
```

Confirm: `board_size 7`, `sub_games 6`, `survival_threshold 35`, `barriers_max 14`,
`email_enabled true`, and the opponent URL is theirs and not `127.0.0.1`.

**4. Warm-up match.** Rule 52 allows unlimited warm-ups against the same
opponent; only one match per opponent counts. Set `num_games` to 1 on both sides,
play it, then set both back to 6. Never let the counted match be the first time
the two processes have spoken.

---

## C. The counted match

```bash
uv run python -m p2p_chase peer --role thief
```

(or `--role police` if that is the role you agreed in A1)

Leave it alone. It plays all six sub-games, runs the mutual audit, writes the
four artifacts and emails the report by itself.

---

## D. Immediately afterwards — before you close anything

**1. Both reports sent?** Your console prints `"email": {"sent": true, …}`. Ask
the opponent to confirm theirs sent too. If only one side reports, **neither
team scores** (rule 35).

**2. Signatures match?** Ask them for their `mutual_agreement.sha256` and compare
with yours. Identical means the reports agree. Different means something is
wrong — do not submit both, work out why first.

**3. Verify your own log:**

```bash
uv run python -m p2p_chase verify --log logs/SMNGRP05/log_<game_id>_g01.json
```

**4. Write down**, for the submission form: date, start and end time, opponent
team name, both scores, their declared number of matches played, and their
agent's sending email address.

**5. Back up `logs/SMNGRP05/`** somewhere outside the repo. It is git-ignored by
design, so nothing else preserves it.

---

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `Agreed terms differ… Mismatched keys: [...]` | Their `game.json` differs | Compare that key; usually `num_games` or `map_area` |
| `Opponent MCP server unreachable` | Tunnel down, wrong URL, or they have not started | Check their URL ends in `/mcp`; both sides must be running |
| `Port 8801 already in use` | A previous peer is still alive | `Get-NetTCPConnection -LocalPort 8801 -State Listen` then `Stop-Process -Id <PID>` |
| Match ends `timeout` | Opponent crashed or went silent | Scores 0-0. Replay it — a technical loss helps nobody |
| `"sent": false` in the email block | Gmail auth expired or offline | Artifacts are still on disk; re-send rather than replay the match |

A crash in one sub-game does not lose the series — it is scored as a technical
loss and the remaining sub-games continue.
