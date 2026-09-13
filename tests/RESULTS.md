# Reproducible test results

Run from the repository root (requires `gltest` / `genlayer-test` and Node for frontend checks).

```bash
gltest tests/test_match_guard.py
```

Recorded locally 2026-09-13:

```
collected 27 items
tests/test_match_guard.py ...........................                    [100%]
============================= 27 passed in 2.33s ==============================
```

Config: [`gltest.config.yaml`](../gltest.config.yaml) (`default: localnet`). Contract under test: [`contracts/match_guard.py`](../contracts/match_guard.py).

Frontend (from `frontend/`):

```bash
npm run test:urls
npm run test:money
npm run check:float
```

All three pass: Wikipedia / query-only binding rejected; money helpers stay on `BigInt`; no float math on prize fields.

Critical contract cases in `tests/test_match_guard.py`:

- mismatched `platform_match_id` / non-participant tag
- altered replay hash
- Wikipedia host and query-only `?match=` binding rejected
- duplicate / overlapping / committed-identifier replacement
- failed `web.render` and invalid JSON (stay `CHALLENGED`)
- low-confidence freeze (no evidence replacement)
- timeout recovery + failed payout then `retry_resolution`
- successful `NO_CHEAT` / `CHEAT_CONFIRMED` / unchallenged settlement
