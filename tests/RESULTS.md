# Reproducible test results

Run from the repository root (requires `gltest` / `genlayer-test` ≥ 0.29 and Node for frontend checks):

```bash
gltest tests/test_match_guard.py
```

Recorded locally 2026-09-22 after module-level EthSend wasi patch + contract payout fallback:

```
collected 30 items
tests/test_match_guard.py ..............................                 [100%]
============================= 30 passed in 6.36s ==============================
```

Config: [`gltest.config.yaml`](../gltest.config.yaml) (`default: localnet`). Contract: [`contracts/match_guard.py`](../contracts/match_guard.py).

Payout under test:
- Contract prefers `_EoaRecipient.emit_transfer` (studionet `Send`), then falls back to `gl.get_contract_at(...).emit_transfer` for gltest `_EOAProxy`.
- [`tests/transfer_mock.py`](transfer_mock.py) patches `gltest.direct.wasi_mock._handle_gl_call` for every VM (not only `vm._gl_call_hook`), installed from [`tests/conftest.py`](conftest.py) and at import of `test_match_guard.py`.

Critical cases covered (must stay green):

- adjudication: unchallenged, `NO_CHEAT`, `CHEAT_CONFIRMED`
- low-confidence freeze + blocked rechallenge
- failed-transfer → `PAYOUT_FAILED` → `retry_resolution` (unchallenged, no-cheat, cheat, expired, timeout)
- balance / prize + `payout_recipient` conservation
- Wikipedia / encyclopedia blocked; allowlisted path-bound records only

Frontend (from `frontend/`):

```bash
npm run test:urls
npm run test:money
npm run check:float
```
