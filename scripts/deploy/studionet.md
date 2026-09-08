# Studionet deploy

Deploy from GenLayer Studio **Run & Debug**. Confirm **GenVM Result: SUCCESS**, not only `FINALIZED`.

| Field | Value |
|---|---|
| Network | studionet |
| Address | `0xB53DDd9F969122c05A1BFF099f5a097FD3824Cbc` |
| Explorer | https://explorer-studio.genlayer.com/address/0xB53DDd9F969122c05A1BFF099f5a097FD3824Cbc |

`create_match` must be `@gl.public.write.payable`. A non-payable write that sends GEN fails with:

`ValueError: called non-payable method ... with non-zero value`

Frontend: set `VITE_CONTRACT_ADDRESS` in `frontend/.env` and in Vercel production, then rebuild.
