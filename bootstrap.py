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
