# MatchGuard — Amateur Esports Prize Escrow on GenLayer

Community cups usually leave the prize with the organizer. After the result is posted, a cheat report (aimhack, wallhack, match-fixing) has no neutral referee. MatchGuard holds the GEN in **one contract**, lets a player or organizer declare a winner, then opens a challenge window. If nobody challenges, the prize pays out with **no AI**. If someone challenges with evidence plus two independent sources, GenLayer AI returns a **binary** verdict: `NO_CHEAT` or `CHEAT_CONFIRMED`. Validators compare with absolute equality (`==`) — no percentage tolerance — so consensus settles **exactly one payout**.

MatchGuard does not work without GenLayer: no EVM contract can read unstructured replay/VOD/anti-cheat pages, and no amateur cup can hire a professional anti-cheat desk.

## Live App

https://matchguard-genlayer.vercel.app

## Deployed Contract

- **Network:** studionet (GenLayer Studio hosted)
- **Address:** `0x3c48A5Ed4F3263958A6761FA598635F9Ce435FFD`
- **Explorer:** https://explorer-studio.genlayer.com/address/0x3c48A5Ed4F3263958A6761FA598635F9Ce435FFD

## How to try

1. Open the live app (or `cd frontend && npm run dev`).
2. Install MetaMask. Click **Connect wallet**. The app adds/switches to **studionet** (chain id from `genlayer-js` `chains.studionet`).
3. Fund that address with GEN from the GenLayer Studio **Accounts** panel. Do **not** use `testnet-faucet.genlayer.foundation` — that faucet credits Asimov/Bradbury, not studionet.
4. Create a match. Pick category chips (FPS / MOBA / Fighting / Other), paste two player addresses, a prize chip, a result deadline, and a challenge window (6h / 12h / 24h / 48h, plus a 2-minute demo). Prize strings are parsed with `parseGenToWei` (no float).
5. Share the `?match=<id>` link. A player or the organizer declares **A** or **B** before the deadline.
6. The UI shows the challenge countdown. If it closes with no challenge, anyone can click **Claim prize**. If a player challenges, paste ≥1 evidence URL + ≥2 independent public URLs, then **Request AI adjudication**. Consensus is slower than a normal write — wait for the spinner.
7. Read the verdict + `reason` + confidence. Open the tx on [Explorer](https://explorer-studio.genlayer.com/address/0x3c48A5Ed4F3263958A6761FA598635F9Ce435FFD). Confirm **GenVM Result: SUCCESS**, not only `FINALIZED`. Use two Wikipedia pages for a challenge — JS-heavy sites (HLTV, Twitter) make `web.render` fail.

**Expected outcome:** `AWAITING_RESULT` → `RESULT_DECLARED` → either `RESOLVED_UNCHALLENGED` (no challenge) or `CHALLENGED` → `RESOLVED_NO_CHEAT` / `RESOLVED_CHEAT_CONFIRMED`. Low confidence (`< 60`) becomes `DISPUTED_LOW_CONFIDENCE` so a player can re-challenge with new evidence (while the window is still open). Transfer failure becomes `PAYOUT_FAILED` with a retry that does **not** re-run AI. If nobody declares before the deadline, the organizer claims `EXPIRED_REFUNDED`.

---

## Why one contract and a binary verdict

- **One contract holds the GEN.** Multi-contract designs previously trapped funds when a cross-contract call did not forward `value`. The organizer sends GEN straight into MatchGuard; the contract pays out with `emit_transfer`.
- **Two discrete outcomes, no percentages.** A prior project (JobVerdict) was rejected because %-tolerance consensus let two validators “agree” while settling two different amounts. MatchGuard only allows `NO_CHEAT` / `CHEAT_CONFIRMED`. Unchallenged payouts skip AI entirely.

---

## Resolution flow

1. **Create match** — `create_match` (payable) + `gl.message.value` = prize. Status: `AWAITING_RESULT`.
2. **Share** `?match=<id>` with both players.
3. **Declare result** — player or organizer calls `declare_result` with `A` or `B` before `result_deadline`. Status: `RESULT_DECLARED`.
4. **Challenge window** — a player may `challenge_result` with ≥1 evidence URL + ≥2 independent reference URLs.
5. **No challenge** — after the window, anyone calls `finalize_unchallenged_payout` → prize to declared winner → `RESOLVED_UNCHALLENGED`. No AI.
6. **Challenge** — `resolve_challenge` runs `gl.vm.run_nondet`:
   - Leader: `gl.nondet.web.render` every URL, `gl.nondet.exec_prompt`, parse JSON `{verdict, confidence, reason}`.
   - Validator: `my.verdict == leader.verdict` (absolute) and the same `confidence >= 60` branch.
7. `confidence < 60` → `DISPUTED_LOW_CONFIDENCE` (re-challenge, no payout).
8. `NO_CHEAT` → prize to declared winner → `RESOLVED_NO_CHEAT`. `CHEAT_CONFIRMED` → prize to the other player → `RESOLVED_CHEAT_CONFIRMED`.
9. Transfer fail → `PAYOUT_FAILED`. `retry_resolution` reuses the stored verdict/declared winner and **does not re-run AI**.
10. No result before deadline → organizer `claim_expired_refund` → `EXPIRED_REFUNDED`.

---

## Verified APIs (do not invent new ones)

| Task | Correct API | Do not use |
|---|---|---|
| Caller | `gl.message.sender_address` | `gl.message.sender` |
| Send GEN | `gl.get_contract_at(addr).emit_transfer(value=u256(amount))` | `gl.transfer(...)` |
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
npm run check:float
```

Coverage includes: unchallenged payout after the window, NO_CHEAT keeps the declared winner, CHEAT_CONFIRMED reverses the winner, expired refund, declare after deadline, challenge after window closed, missing URLs, low-confidence DISPUTED then re-challenge, web fail / broken JSON, double-declare / double-challenge / double-resolve, and real `emit_transfer` exceptions on unchallenged / NO_CHEAT / CHEAT_CONFIRMED / expired-refund → `PAYOUT_FAILED` → successful `retry_resolution`.

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
