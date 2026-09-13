# Studionet deploy

Deploy from GenLayer Studio **Run & Debug**. Confirm **GenVM Result: SUCCESS**, not only `FINALIZED`.

| Field | Value |
|---|---|
| Network | studionet |
| Address | `0x9E436D9f8DB42C834FD906EBE9E95F48aB267571` |
| Explorer | https://explorer-studio.genlayer.com/address/0x9E436D9f8DB42C834FD906EBE9E95F48aB267571 |

`create_match` must be `@gl.public.write.payable`. A non-payable write that sends GEN fails with:

`ValueError: called non-payable method ... with non-zero value`

Frontend: set `VITE_CONTRACT_ADDRESS` in `frontend/.env` and in Vercel production, then rebuild.
