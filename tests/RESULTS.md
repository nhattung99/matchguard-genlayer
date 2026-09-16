# Reproducible test results

Run from the repository root (requires `gltest` / `genlayer-test` and Node for frontend checks).

```bash
gltest tests/test_match_guard.py
```

Recorded locally 2026-09-16 after explicit Wikipedia encyclopedia block:

```
collected 30 items
tests/test_match_guard.py ..............................                 [100%]
============================= 30 passed in 14.63s ==============================
```

Config: [`gltest.config.yaml`](../gltest.config.yaml) (`default: localnet`). Contract under test: [`contracts/match_guard.py`](../contracts/match_guard.py).

Frontend (from `frontend/`):

```bash
npm run test:urls
npm run test:money
npm run check:float
```

Critical contract cases in `tests/test_match_guard.py`:

- mismatched `platform_match_id` / non-participant tag
- altered replay hash
- Wikipedia host, query-only `?match=` binding, and unallowlisted issuers rejected
- `test_critical_match_specific_evidence_model`: generic Wikipedia without match ID rejected; Wikipedia with match ID still rejected; create requires game + external match ID; declare stores committed official/replay identifiers
- duplicate / overlapping / committed-identifier replacement
- failed `web.render` and invalid JSON (stay `CHALLENGED`)
- low-confidence freeze (no evidence replacement)
- timeout recovery + failed payout then `retry_resolution`
- successful `NO_CHEAT` / `CHEAT_CONFIRMED` / unchallenged settlement
- `PAYOUT_FAILED` preserves verdict + `payout_recipient`; retry does not re-run AI
- prize-amount conservation across NO_CHEAT and CHEAT_CONFIRMED
