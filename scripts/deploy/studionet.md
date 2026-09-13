# Studionet deploy

Deploy from GenLayer Studio **Run & Debug**. Confirm **GenVM Result: SUCCESS**, not only `FINALIZED`.

| Field | Value |
|---|---|
| Network | studionet |
| Address | `0x96C3EeFd87855Df9765ABCA688946456c284c899` |
| Explorer | https://explorer-studio.genlayer.com/address/0x96C3EeFd87855Df9765ABCA688946456c284c899 |
| Constructor | SUCCESS (2026-09-13) |

This revision: `ALLOWED_RECORD_HOSTS`, `_EoaRecipient.emit_transfer`, stored `payout_recipient`.

`create_match` must be `@gl.public.write.payable`. A non-payable write that sends GEN fails with:

`ValueError: called non-payable method ... with non-zero value`

Frontend: set `VITE_CONTRACT_ADDRESS` in `frontend/.env` and in Vercel production, then rebuild.
