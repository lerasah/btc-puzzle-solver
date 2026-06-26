#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate hypotheses.json for run_batch.py.

Takes the 8 high-confidence words and pairs them with every CHOOSE-combination of
the optional pool, sorted most-likely-first (so the batch tests the strongest word
sets before the weaker ones). Each job = 8 strong words + CHOOSE optional = 12.

Examples:
    python3 gen_hypotheses.py                      # 8 strong + choose 4 from top 8 -> 70 jobs
    python3 gen_hypotheses.py --pool-size 12       # top 12 optional -> 495 jobs
    python3 gen_hypotheses.py --pool-size 16 --max 300   # widest pool, cap at 300 jobs
"""
import itertools, json, argparse, os

# 8 words we're confident are in the seed (locked into every job).
STRONG = ["moon", "tower", "food", "only", "real", "black", "subject", "this"]

# Remaining BIP39-valid words from the image, in rough PRIORITY order
# (banner/thematic words first, BLM-slogan leftovers last).
OPTIONAL_PRIORITY = ["order", "brave", "world", "phrase", "seed", "find",
                     "first", "future", "welcome", "picture", "peace", "one",
                     "more", "end", "matter", "police"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--choose", type=int, default=4,
                    help="optional words per job (12 - len(STRONG)); default 4")
    ap.add_argument("--pool-size", type=int, default=8,
                    help="use the top-N priority optional words (default 8 -> 70 jobs)")
    ap.add_argument("--max", type=int, default=0, help="cap number of jobs (0 = no cap)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "hypotheses.json"))
    a = ap.parse_args()

    if len(STRONG) + a.choose != 12:
        print(f"[warn] {len(STRONG)} strong + {a.choose} optional = "
              f"{len(STRONG)+a.choose} (not 12).")

    pool = OPTIONAL_PRIORITY[:a.pool_size]
    rank = {w: i for i, w in enumerate(OPTIONAL_PRIORITY)}
    combos = list(itertools.combinations(pool, a.choose))
    combos.sort(key=lambda c: sum(rank[w] for w in c))   # most-likely combinations first
    if a.max > 0:
        combos = combos[:a.max]

    jobs = [{"label": f"h{idx:04d}_" + "_".join(c),
             "overrides": {"KNOWN_WORDS": STRONG, "OPTIONAL_WORDS": list(c)}}
            for idx, c in enumerate(combos, 1)]

    with open(a.out, "w") as f:
        json.dump(jobs, f, indent=2)
    print(f"wrote {len(jobs)} hypotheses to {a.out}")
    print(f"(strong={len(STRONG)} + choose {a.choose} from top {len(pool)} optional, "
          f"priority-sorted)")


if __name__ == "__main__":
    main()
