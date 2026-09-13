# MatchGuard — Amateur Esports Prize Escrow on GenLayer

Community cups usually leave the prize with the organizer. After the result is posted, a cheat report (aimhack, wallhack, match-fixing) has no neutral referee. MatchGuard holds the GEN in **one contract**, lets a player or organizer declare a winner, then opens a challenge window. If nobody challenges, the prize pays out with **no AI**. If someone challenges with evidence plus two independent sources, GenLayer AI returns a **binary** verdict: `NO_CHEAT` or `CHEAT_CONFIRMED`. Validators compare with absolute equality (`==`) — no percentage tolerance — so consensus settles **exactly one payout**.

MatchGuard does not work without GenLayer: no EVM contract can read unstructured replay/VOD/anti-cheat pages, and no amateur cup can hire a professional anti-cheat desk.

## Live App

https://matchguard-genlayer.vercel.app

## Deployed Contract

- **Network:** studionet (GenLayer Studio hosted)
- **Address:** `0x96C3EeFd87855Df9765ABCA688946456c284c899`
- **Explorer:** https://explorer-studio.genlayer.com/address/0x96C3EeFd87855Df9765ABCA688946456c284c899
- **Source on GitHub:** [`contracts/match_guard.py`](contracts/match_guard.py) — this file is the Studio deploy (allowlisted issuers + `_EoaRecipient` EOA payout). Constructor **SUCCESS** on 2026-09-13.

### Live proof (Match #1)

| Step | Method | GenVM | Tx |
|---|---|---|---|
| Create | `create_match` (1 GEN) | SUCCESS | https://explorer-studio.genlayer.com/tx/0x204ae640b34971e22f9f80609f9ab7396952b5d0934b7e8d0fa617c53050ca5e |
| Declare | `declare_result` | SUCCESS | https://explorer-studio.genlayer.com/tx/0xc05f4c4e62e920efcbd716d3ddc55c33f725a97e0d9c1430baa5e8387ab27bf7 |
| Challenge | `challenge_result` (allowlisted demo records) | SUCCESS | https://explorer-studio.genlayer.com/tx/0xcde2fea8fd18dc2d0c218faaa9b643df112efb31c120b9366f9773048c0300dc |
| Adjudicate | `resolve_challenge` | SUCCESS | https://explorer-studio.genlayer.com/tx/0xf8f3d81fe0f5efea9722e923ceb327169e22c252abec665d0295430b0ce4b937 |
| Payout | native **Send** 1 GEN to declared winner | FINALIZED (not an IC child ERROR) | https://explorer-studio.genlayer.com/tx/0x2706b80bb337f95e1dbf2b3711c039e888e7ab96e73e81fd8a89de2e4c1cc92c |

UI: `RESOLVED_NO_CHEAT` / `NO_CHEAT` / confidence 100 / `payout_recipient` = winner. Contract escrow is **0 GEN**. Payout uses `_EoaRecipient(Address).emit_transfer` (Explorer type `Send`). If a transfer still throws, status is `PAYOUT_FAILED`, `verdict` + `payout_recipient` stay stored, and permissionless `retry_resolution` pays without re-running AI.

## How to try

1. Open the live app (or `cd frontend && npm run dev`).
2. Install MetaMask. Click **Connect wallet**. The app adds/switches to **studionet** (chain id from `genlayer-js` `chains.studionet`).
3. Fund that address with GEN from the GenLayer Studio **Accounts** panel. Do **not** use `testnet-faucet.genlayer.foundation` — that faucet credits Asimov/Bradbury, not studionet.
4. Create a match. Enter game title, platform/tournament match ID, both player addresses **and** in-game tags, match timestamp, required 64-hex replay hash (integrity only), prize, deadline, and challenge window. Prize strings are parsed with `parseGenToWei` (no float).
5. Share the app `?match=<id>` link (UI only). A player or the organizer declares **A** or **B** before the deadline, committing an **official result URL** and a distinct **replay/VOD URL**. Both must be `https://` records from an **on-chain allowlisted** issuer (`get_approved_hosts`: FACEIT, start.gg, ESL, Challonge, Toornament, Battlefy, ESEA, or MatchGuard demo) whose **path** contains `platform_match_id`. Wikipedia, unallowlisted hosts, and query-string `?match=` binding are rejected.
6. The UI shows the challenge countdown. If it closes with no challenge, anyone can click **Claim prize**. If a player challenges, the claimed match ID and player tag must match the committed identity. Paste 1 match-linked evidence record + 2 distinct match-linked references (https, path-bound, no overlap with committed official/replay), pick `PLATFORM_API` / `ANTI_CHEAT` / `ORGANIZER`, then **Request AI adjudication**. Demo records: `https://matchguard-genlayer.vercel.app/records/FACEIT-CS2-88421/`. HLTV/Twitter/YouTube fail `web.render`.
7. Read the verdict + `reason` + confidence. Open the tx on [Explorer](https://explorer-studio.genlayer.com/address/0x96C3EeFd87855Df9765ABCA688946456c284c899). Confirm **GenVM Result: SUCCESS**, not only `FINALIZED`. Evidence is **frozen** once a challenge starts. If AI stays in `CHALLENGED` or `DISPUTED_LOW_CONFIDENCE` past the timeout, anyone can call **Timeout refund to organizer**.

**Expected outcome:** `AWAITING_RESULT` → `RESULT_DECLARED` → either `RESOLVED_UNCHALLENGED` (no challenge) or `CHALLENGED` → `RESOLVED_NO_CHEAT` / `RESOLVED_CHEAT_CONFIRMED`. Low confidence (`< 60`) becomes `DISPUTED_LOW_CONFIDENCE` with evidence frozen (no replacement). If AI never reaches a terminal verdict, permissionless `recover_unresolved_escrow` returns the prize to the organizer as `RESOLVED_TIMEOUT_REFUND`. Transfer failure becomes `PAYOUT_FAILED` with a retry that does **not** re-run AI. If nobody declares before the deadline, the organizer claims `EXPIRED_REFUNDED`. Replay/VOD hash is integrity evidence only — not proof of cheat. `ORGANIZER` attestation is a disclosed trust assumption; the opposing player files the challenge as the response path.

---

## Why one contract and a binary verdict

- **One contract holds the GEN.** Multi-contract designs previously trapped funds when a cross-contract call did not forward `value`. The organizer sends GEN straight into MatchGuard; the contract pays out with `emit_transfer`.
- **Two discrete outcomes, no percentages.** A prior project (JobVerdict) was rejected because %-tolerance consensus let two validators “agree” while settling two different amounts. MatchGuard only allows `NO_CHEAT` / `CHEAT_CONFIRMED`. Unchallenged payouts skip AI entirely.

---

## Resolution flow

1. **Create match** — `create_match` (payable) + `gl.message.value` = prize. Stores `game_title`, `platform_match_id`, player tags, `match_played_at`, required `replay_content_hash`. Status: `AWAITING_RESULT`.
2. **Share** the app `?match=<id>` link with both players (not an evidence URL).
3. **Declare result** — player or organizer calls `declare_result` with `A`/`B` plus allowlisted `official_result_url` and `replay_or_vod_url` (https, host on `ALLOWED_RECORD_HOSTS`, path contains `platform_match_id`). Hash must match create. Status: `RESULT_DECLARED`.
4. **Challenge window** — a player may `challenge_result` with claimed match ID + accused tag + `PLATFORM_API`/`ANTI_CHEAT`/`ORGANIZER` + 1–3 allowlisted evidence records + 2–3 distinct references. Rejects unallowlisted hosts, Wikipedia, query-only binding, mismatch, http/duplicate/overlapping URLs, and any replacement after freeze.
5. **No challenge** — after the window, anyone calls `finalize_unchallenged_payout` → prize to declared winner → `RESOLVED_UNCHALLENGED`. No AI.
6. **Challenge** — `resolve_challenge` runs `gl.vm.run_nondet`:
   - Leader: `gl.nondet.web.render` official + replay + evidence + refs, isolate/truncate page text, `gl.nondet.exec_prompt`, parse JSON `{verdict, confidence, reason}`. Hash is labeled integrity-only. ORGANIZER trust is disclosed in the prompt.
   - Validator: `my.verdict == leader.verdict` (absolute) and the same `confidence >= 60` branch.
7. `confidence < 60` → `DISPUTED_LOW_CONFIDENCE` (evidence frozen, no replacement, no payout).
8. `NO_CHEAT` → prize to declared winner → `RESOLVED_NO_CHEAT`. `CHEAT_CONFIRMED` → prize to the other player → `RESOLVED_CHEAT_CONFIRMED`.
9. If still `CHALLENGED` or `DISPUTED_LOW_CONFIDENCE` after `challenged_at + challenge_window_seconds`, anyone calls `recover_unresolved_escrow` → prize back to organizer → `RESOLVED_TIMEOUT_REFUND`.
10. Transfer fail → `PAYOUT_FAILED`. Verdict and `payout_recipient` stay stored. Permissionless `retry_resolution` pays that recipient and **does not re-run AI**.
11. No result before deadline → organizer `claim_expired_refund` → `EXPIRED_REFUNDED`.

---

## Verified APIs (do not invent new ones)

| Task | Correct API | Do not use |
|---|---|---|
| Caller | `gl.message.sender_address` | `gl.message.sender` |
| Send GEN | `_EoaRecipient(Address).emit_transfer(value=u256(amount))` via `@gl.evm.contract_interface` | `gl.get_contract_at(EOA).emit_transfer` (child GenVM ERROR) or `gl.transfer(...)` |
| Receive GEN with the tx | `@gl.public.write.payable` + `gl.message.value` | `@gl.public.write` without `.payable` when `value > 0` |
| Timestamp | `gl.message.datetime` → `datetime.fromisoformat` → Unix seconds | `gl.block.timestamp` |
| TreeMap default | `map.get(key, default)` | — |

On current Studio GenVM, a non-payable write that sends GEN fails with `ValueError: called non-payable method ... with non-zero value`. `create_match` is therefore `.payable`. (An older note that `.payable` “does not exist” was wrong for the current Studio runner.)

Contract header:

```
# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

---

## Money handling itemize

Every money field is **wei / base units**, `bigint` on-chain and `BigInt` off-chain. No `float` / `parseFloat` / `Math.round` / `Math.floor` / `Math.ceil` near money variables.

| Field | WRITE | READ | Converter |
|---|---|---|---|
| `prize_amount` (contract) | `create_match`: `bigint(gl.message.value)` | `get_match` / `list_matches` return `str(int(prize_amount))` | on-chain `bigint` only |
| Unchallenged / NO_CHEAT payout | `emit_transfer(value=u256(prize_amount))` to declared winner | UI: `formatWeiToGen(prize_amount)` | exact prize, no split % |
| CHEAT_CONFIRMED payout | `emit_transfer(value=u256(prize_amount))` to the other player | same `formatWeiToGen` | exact prize reversed |
| Expired refund | `emit_transfer(value=u256(prize_amount))` to organizer | same | exact prize |
| Retry | same `prize_amount` + stored verdict / declared winner | same | does not re-run AI |
| GEN input on UI | chips / `sanitizeGenInput` → `parseGenToWei` → `writeContract({ value: wei })` | wei preview under the field | string-parse + `BigInt` |
| GEN display | — | `formatWeiToGen(prize_amount)` | `BigInt` divide `10^18n` |
| `result_deadline` / `challenge_window_seconds` | unix seconds (`u256`), **not money** | chip offset → `BigInt(Date.now()) / 1000n` | does not use money helpers |

`parseGenToWei` / `formatWeiToGen` live in [`frontend/src/money.js`](frontend/src/money.js). Float guard: [`scripts/check-no-float-money.js`](scripts/check-no-float-money.js) on `prebuild`.

---

## Deploy on studionet

Deploy from the GenLayer Studio **Run & Debug** panel. Details: [`scripts/deploy/studionet.md`](scripts/deploy/studionet.md).

1. Open [GenLayer Studio](https://studio.genlayer.com).
2. New Intelligent Contract → paste [`contracts/match_guard.py`](contracts/match_guard.py).
3. Confirm the two header lines (`v0.2.16` + `Depends` hash) match the current Studio template. If Studio ships a newer hash, update the Depends line and redeploy.
4. Run & Debug → Deploy. Click the transaction and confirm **`Result: SUCCESS`**.
5. Set `VITE_CONTRACT_ADDRESS` in `frontend/.env` and in Vercel production env, then rebuild.

```bash
cd frontend
cp .env.example .env
# set VITE_CONTRACT_ADDRESS
npm install
npm run dev
```

Without an address the UI stays in preview mode (banner, no white crash).

---

## Tests

```bash
gltest tests/test_match_guard.py
npm run test:money
npm run test:urls
npm run check:float
```

Latest recorded run: see [`tests/RESULTS.md`](tests/RESULTS.md). Config: [`gltest.config.yaml`](gltest.config.yaml).

Coverage includes: unchallenged payout after the window, NO_CHEAT keeps the declared winner, CHEAT_CONFIRMED reverses the winner, expired refund, declare after deadline, challenge after window closed, missing URLs, mismatched match IDs, participant mismatch, altered replay hash, Wikipedia / query-only / unallowlisted-host binding rejected, unbound/http/duplicate/overlapping sources, evidence freeze after low-confidence, failed rendering / broken JSON, double-declare / double-challenge / double-resolve, permissionless timeout refund for stuck CHALLENGED and DISPUTED_LOW_CONFIDENCE, prize-amount conservation across NO_CHEAT + CHEAT_CONFIRMED, and real `emit_transfer` exceptions on unchallenged / NO_CHEAT / CHEAT_CONFIRMED / expired-refund / timeout-refund → `PAYOUT_FAILED` (verdict + `payout_recipient` preserved) → successful `retry_resolution`.

---

## Layout

```
contracts/match_guard.py       # Intelligent Contract (single file, holds GEN)
tests/test_match_guard.py      # gltest + sim_installMocks
frontend/src/                  # Vite + React
frontend/src/money.js          # parseGenToWei / formatWeiToGen
scripts/deploy/studionet.md    # live studionet address (fill after deploy)
scripts/check-no-float-money.js
```
