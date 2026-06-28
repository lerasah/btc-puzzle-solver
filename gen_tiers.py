#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiered hypothesis generator (separate from gen_hypotheses.py / the original 70).

Locks a high-confidence CORE and chooses the remaining words from priority-ordered
TIERS of weaker candidates (the "element" words people derived from the image
objects + the Reddit 'correct-8' extras). Outputs to a SEPARATE file with a
't12_' label prefix so it never collides with the original h00xx jobs' folders.

CORE rationale: these 7 appear in BOTH our image analysis AND the Reddit user's
12-word guess that another solver said had "8 correct" — so they're the highest
cross-validated picks. The disputed 8th (only/time/save/actual/march) is left to
the tiers, so the generator can discover it instead of us guessing.

Run:
    python3 gen_tiers.py                 # choose 5 from tiers, cap 500 -> hypotheses_tiers.json
    python3 gen_tiers.py --max 2000      # more jobs
    python3 gen_tiers.py --core-size 8 --add-only   # lock 'only' too, choose 4
Then point a NEW batch / new pods at it (leave the original 70 running):
    HYPOTHESES_FILE=hypotheses_tiers.json python3 run_batch.py
"""
import itertools, json, argparse, os
from mnemonic import Mnemonic

WL = set(Mnemonic("english").wordlist)

CORE = ["moon", "tower", "food", "black", "real", "subject", "this"]   # locked every job

# Optional candidates grouped by tier, highest priority first. 'kneel' is dropped
# automatically (not a BIP39 word); everything else here is valid.
TIERS = [
    # A: statue-base word + the Reddit 'correct-8' extras
    ["only", "time", "save", "actual", "march"],
    # B: image-object / slogan words (BLM, election, surveillance)
    ["matter", "peace", "eye", "vote", "select", "choice", "one", "gun", "camera"],
    # C: thematic / whitepaper / banner words
    ["history", "future", "first", "order", "world", "brave", "proof", "state",
     "zero", "power", "crowd", "knee", "gate", "wall", "person"],
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-len", type=int, default=12)
    ap.add_argument("--core-size", type=int, default=7,
                    help="how many CORE words to lock (7 default; 8 adds 'only' if --add-only)")
    ap.add_argument("--add-only", action="store_true",
                    help="include 'only' in the locked core (use with --core-size 8)")
    ap.add_argument("--max", type=int, default=500, help="cap number of jobs (0 = no cap)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "hypotheses_tiers.json"))
    a = ap.parse_args()

    if a.seed_len != 12:
        raise SystemExit("gen_tiers.py builds 12-word combination jobs only. For 24-word, "
                         "fill in hypotheses_24_template.json by hand (24! can't be brute-forced; "
                         "you must lock the order). See README.")

    core = list(CORE)
    if a.add_only and "only" not in core:
        core = core + ["only"]
    core = core[:a.core_size] if a.core_size <= len(core) else core

    # priority-ordered, BIP39-filtered pool, excluding anything already in core
    pool, rank = [], {}
    for w in [w for tier in TIERS for w in tier]:
        if w in WL and w not in core and w not in rank:
            rank[w] = len(pool); pool.append(w)

    choose = a.seed_len - len(core)
    if choose < 0 or choose > len(pool):
        raise SystemExit(f"Can't choose {choose} from a pool of {len(pool)}.")

    combos = list(itertools.combinations(pool, choose))
    combos.sort(key=lambda c: sum(rank[w] for w in c))      # most-likely combos first
    if a.max > 0:
        combos = combos[:a.max]

    jobs = [{"label": "t12_%04d_%s" % (i, "_".join(c)),
             "overrides": {"SEED_LEN": a.seed_len, "KNOWN_WORDS": core, "OPTIONAL_WORDS": list(c)}}
            for i, c in enumerate(combos, 1)]

    with open(a.out, "w") as f:
        json.dump(jobs, f, indent=2)
    print(f"wrote {len(jobs)} hypotheses to {a.out}")
    print(f"core (locked, {len(core)}): {core}")
    print(f"choose {choose} from pool of {len(pool)}: {pool}")
    print("labels use the 't12_' prefix -> separate job folders, won't touch the original 70.")


if __name__ == "__main__":
    main()
