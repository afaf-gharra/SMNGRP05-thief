# A real match, in four files

These are the actual artifacts from a two-process match played over real MCP
HTTP transport on 2026-07-29 — not hand-written examples. `uoh-ag12` is this
team; `rival-01` is a second instance of the agent standing in for an opponent.

| File | What it is |
|---|---|
| `declaration_<game_id>.json` | Both teams' identity, hardware, models and repositories, signed before play |
| `config_<game_id>_g<NN>.json` | The agreed terms for each sub-game, with its SHA-256 lock |
| `log_<game_id>_g<NN>.json` | Every sealed step, with nonces revealed for audit |
| `result_<game_id>.json` | Per-sub-game scores and the aggregate, with the mutual signature |

Two sub-games, roles alternating, both ending in survival: 15 points each plus
the tie bonus of 2, so 17–17. The opposing peer produced a byte-identical
`mutual_agreement.sha256`, which is the condition the book requires for a match
to count for either team.

Verify the commit chain yourself:

```bash
uv run python -m p2p_chase verify --log docs/sample-run/log_rival-01-vs-uoh-ag12_g01.json
```
