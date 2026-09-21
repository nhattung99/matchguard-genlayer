# Reproducible test results

Run from the repository root (requires `gltest` / `genlayer-test` and Node for frontend checks):

```bash
gltest tests/test_match_guard.py
```

Recorded locally 2026-09-21 after deterministic EthSend harness for `_EoaRecipient` payouts:

```
collected 30 items
tests/test_match_guard.py ..............................                 [100%]
============================= 30 passed in 2.64s ==============================
```

Config: [`gltest.config.yaml`](../gltest.config.yaml) (`default: localnet`). Contract under test: [`contracts/match_guard.py`](../contracts/match_guard.py).

EthSend / transfer mocks live in [`tests/transfer_mock.py`](transfer_mock.py) and are installed by [`tests/conftest.py`](conftest.py) so adjudication, retry, and balance cases do not depend on an unknown `gl_call`.

Frontend (from `frontend/`):

```bash
npm run test:urls
npm run test:money
npm run check:float
```

Critical contract cases in `tests/test_match_guard.py`:

- `NO_CHEAT` / `CHEAT_CONFIRMED` adjudication and unchallenged payout
- low-confidence freeze (no evidence replacement)
- failed transfer → `PAYOUT_FAILED` → `retry_resolution` (unchallenged, no-cheat, cheat-confirmed, expired, timeout)
- prize-amount / payout-recipient conservation across NO_CHEAT and CHEAT_CONFIRMED
- Wikipedia / encyclopedia hosts blocked; query-only and unallowlisted issuers rejected
- committed `platform_match_id`, game title, tags, official/replay identifiers
- timeout recovery for stuck CHALLENGED / DISPUTED_LOW_CONFIDENCE
