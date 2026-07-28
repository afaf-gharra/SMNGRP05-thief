# Architecture and design decisions

## C4 — Level 1: context

```
   ┌──────────────────┐        signed MCP protocol        ┌──────────────────┐
   │   OUR AGENT      │◄─────── over ngrok tunnels ──────►│ OPPONENT AGENT   │
   │   (this repo)    │      negotiate / turn / audit     │ (another team)   │
   └────────┬─────────┘                                   └─────────┬────────┘
            │ four signed JSON artifacts                            │
            └──────────────────► lecturer's mailbox ◄───────────────┘
                                 (Gmail API, send-only)

   No third process exists. There is no server in the middle of that arrow.
```

## C4 — Level 2: containers

```
  ┌─────────────────────── one peer process ────────────────────────┐
  │  CLI  ──┐                                                       │
  │  GUI  ──┼──► ChaseSdk ──► Orchestrator ──┬──► PeerRuntime       │
  │         │   (sole entry)   (sole gateway)│    (one sub-game)    │
  │         │                                ├──► DeadlineTracker   │
  │         │                                ├──► Watchdog (thread) │
  │         │                                └──► report/emit       │
  │                                                                 │
  │  McpTransport ◄──► FastMCP server (own port, own inboxes)       │
  └─────────────────────────────────────────────────────────────────┘
```

## C4 — Level 3: components inside a runtime

```
  PeerRuntime
    ├── OwnGameState      my position, my barriers, my log  (local truth only)
    ├── BeliefGrid        b(s) over the opponent's cell
    ├── SmellField ×2     mine (emitted) and theirs (absorbed)
    ├── TrustEstimator    Beta-Bernoulli honesty model of this opponent
    ├── GamePhaseMachine  refuses illegal transitions
    ├── TurnHandler       incoming message → belief, scent, barriers, trust
    ├── turn_sender       decide → apply → seal → deposit → send
    └── Brain (strategy)  ◄── the graded seam, swapped by config
            └── Talker    ◄── template | claude_api | ollama | claude_cli
```

**Dependency rule.** `domain` imports nothing outward and performs no I/O.
`strategy` depends on `domain`. `peer` depends on both. `infra` is the only place
that touches a socket, a subprocess or a mailbox. Nothing imports `gui`.

---

## Architecture decision records

### ADR-1 — Each peer runs its own server; there is no game server

**Context.** A central server is the obvious design and is what most game code does.
**Decision.** Fully symmetric peers, each an MCP server *and* client.
**Consequences.** No single point of failure and no single point of trust, at the
cost of every disagreement needing a cryptographic rather than an administrative
resolution. This is the book's core requirement and it drives ADR-2 and ADR-4.
**Rejected.** A "neutral" third process — whoever runs it can change outcomes.

### ADR-2 — Commit-reveal with canonical JSON

**Context.** Each peer is both player and score-keeper for its own moves.
**Decision.** Seal `SHA-256(canonical_json(payload) ‖ nonce)`; reveal nonces only
at the final audit.
**Consequences.** Time-travel, retroactive edits and denial all become detectable.
Canonical form (sorted keys, fixed separators) is **load-bearing**: two
independently written implementations must hash byte-identical input or every
honest game would look like fraud.
**Rejected.** Signing with asymmetric keys — heavier, needs key distribution, and
buys nothing here since identity is already fixed by the fixture.

### ADR-3 — The move is Python; the model only talks

**Context.** The book permits a model in the loop and warns it hallucinates in
Cartesian space.
**Decision.** `_decide_move` is pure Python. The model, if enabled, writes hints
and profiles the opponent — after the move is already chosen and sealed.
**Consequences.** A bad completion can produce a weak sentence, never an illegal
move. Also makes matches free, fast and reproducible by default.
**Rejected.** Model-chosen moves — one hallucinated coordinate is a forfeit.

### ADR-4 — Signed terms, not a config convention

**Context.** Two copies of the rules that differ by one value produce two
irreconcilable realities halfway through a match.
**Decision.** Hash the agreed terms and exchange signatures before the first move;
refuse to play on any mismatch, naming the differing keys.
**Consequences.** Configuration errors surface in the handshake instead of as
inexplicable divergence. **Constraint:** the signed key set is frozen by
interoperability — see ADR-8.

### ADR-5 — A state machine for turn phases

**Context.** Deadlock produces no error and no log line; it is the one failure that
cannot be debugged after the fact.
**Decision.** An explicit transition table; illegal transitions raise. Every
communication phase has an edge to `TECHNICAL_LOSS`.
**Consequences.** Protocol bugs become loud exceptions during development rather
than silent hangs during a fixture. Caught a real bug: a game ending on our own
move had no legal path to the audit phase.

### ADR-6 — Deadlines *and* a watchdog

**Context.** They guard different failures.
**Decision.** `DeadlineTracker` bounds each wait; a `Watchdog` thread bounds the
whole loop and persists state before shutting down.
**Consequences.** A hung provider inside a C extension — invisible to any in-loop
check — still ends in a reportable result rather than a lost afternoon.

### ADR-7 — Barriers valued structurally, not by immediate gain

**Context.** Our first planner demanded a large immediate cell reduction and
therefore **never built a wall**, capturing 0 % against our own thief.
**Decision.** Value = cells removed + anchoring + cut-vertex bonus + occupancy
probability, with vetoes against self-isolation.
**Consequences.** Capture rate went from 0 % to 32 % against our strongest thief
and from 13 % to 57 % against a reference-style one. See
[RESEARCH-REPORT.md](RESEARCH-REPORT.md).

### ADR-8 — Interoperability over elegance on the wire

**Context.** We would like extra fields — an emission-shape selector, a protocol
version, richer claims.
**Decision.** The `TurnMessage` field set and the signed-terms dictionary are
**frozen** to match the reference implementation exactly. Our extensions live in
the sealed payload (which only we hash) and in the private TOML.
**Consequences.** We can shake hands with any team in the league. A test asserts
the exact frozen key sets so a well-meaning refactor cannot break the league.

### ADR-9 — Follow the book where the reference code contradicts it

**Context.** Two genuine conflicts. Scent decay: the book gives
`τ(t+1) = (1−ρ)·τ(t)`, multiplicative; the reference subtracts a constant. Sub-games
per series: Appendix F fixes 6, the reference ships 1.
**Decision.** The book governs, as it states. Decay is multiplicative; the default
series is 6.
**Consequences.** A single deposit stays readable for six to seven turns, matching
the book's own figure; subtraction would empty the board in nine and change the
game materially. Neither choice breaks interoperability, because each peer's decay
only shapes the field it broadcasts about itself.

### ADR-10 — Two repositories, one engine

**Context.** Rule 49 mandates separate police and thief repositories; rule 1
mandates separate processes; roles alternate every sub-game.
**Decision.** Both repositories carry the full symmetric engine and differ in
default role and network configuration.
**Consequences.** Duplication across the two repositories is forced by the rules
rather than accidental — an agent that could only play one role could not
complete a series at all. Documented in both READMEs.

---

## Data contracts

**On the wire** (frozen): `TurnMessage`, `ControlMessage`, `AuditPayload` in
[`domain/protocol.py`](../src/p2p_chase/domain/protocol.py).

**On disk**: the four artifacts in [`report/artifacts.py`](../src/p2p_chase/report/artifacts.py),
named `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`,
`log_<game_id>_g<NN>.json`, `result_<game_id>.json`.

**The symmetric-signature rule.** Both teams must produce an identical
`mutual_agreement.sha256` or the lecturer sees contradicting reports and voids the
match for both. So that hash covers only symmetric facts — roles, outcomes,
scores, aggregate — and deliberately excludes wall-clock timestamps and per-peer
token counts, which legitimately differ between two machines.

## Testing strategy

Unit tests mirror `src/`. The integration suite plays complete series through the
real orchestrator over a loopback transport implementing the same five methods as
the MCP one — so the protocol, the commit chain and the artifacts are exercised
for real while remaining fast and deterministic. `scripts/arena.py` supplies the
statistical evidence for strategy claims.
