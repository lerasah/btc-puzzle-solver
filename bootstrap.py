#!/usr/bin/env python3
# Pod entrypoint. FIRST_PASS toggles a fast no-passphrase / BIP44-only sweep
# without editing puzzle_solver.py, then launches the batch.
import os
import puzzle_solver as ps
import run_batch

mode = os.environ.get("FIRST_PASS", "1").strip().lower()
if mode in ("1", "true", "yes", "on"):
    ps.CONFIG["PASSPHRASES"] = [""]
    ps.CONFIG["DERIVATIONS"] = ["bip44"]
    print("[bootstrap] FIRST_PASS=ON  -> no passphrase, BIP44 only (fast word-set sweep)")
else:
    print("[bootstrap] FIRST_PASS=OFF -> full passphrase/scheme sweep (from CONFIG)")
run_batch.main()
