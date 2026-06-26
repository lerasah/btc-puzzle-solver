#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
0.2 BTC puzzle solver  -  target 1KfZGvwZxsvSmemoCmEV75uqcNzYBHjkHZ

Searches: choose (SEED_LEN - len(KNOWN_WORDS)) words from OPTIONAL_WORDS, then try
every ordering of the resulting 12-word set (optionally with some positions locked),
filtered by BIP39 checksum, across several derivation paths and a passphrase list.

NOT a wallet brute-forcer: it only explores orderings/subsets of a fixed candidate
pool you read off the puzzle image. A random 12-word seed is 2**128 and uncrackable.

Quick start (RunPod / any Linux):
    pip install bip-utils
    export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/XXX/YYY"   # optional
    python3 puzzle_solver.py --selftest      # validate derivation + search + webhook
    python3 puzzle_solver.py                 # the real run (uses CONFIG below)

Survive disconnects:  use tmux/nohup. Progress is checkpointed; re-running resumes.
"""

import argparse, itertools, json, math, os, sys, time, urllib.request
import multiprocessing as mp
from datetime import datetime, timezone

from bip_utils import (Bip39MnemonicValidator, Bip39SeedGenerator,
                       Bip44, Bip44Coins, Bip44Changes,
                       Bip32Slip10Secp256k1, P2PKHAddr, Bip32KeyIndex)

# ============================== CONFIG ==============================
CONFIG = dict(
    TARGET        = "1KfZGvwZxsvSmemoCmEV75uqcNzYBHjkHZ",
    SEED_LEN      = 12,

    # Words you're confident are IN the seed (order unknown unless locked below).
    KNOWN_WORDS   = ["moon","tower","food","only","real","black","subject","this"],

    # The remaining (SEED_LEN - len(KNOWN_WORDS)) words are chosen from this pool.
    # DEFAULT below = exactly 4 words -> choose 4 -> ONE 12-word set (feasible on CPU,
    # ~tens of minutes on a big pod across all passphrases/schemes).
    # TO WIDEN (GPU territory): add words from the full pool and the set count explodes
    #   choose 4 from these 4  -> 1 set
    #   choose 4 from 16       -> 1,820 sets  (months on CPU; needs a CUDA kernel)
    # Full BIP39-valid pool found in the image (drop into OPTIONAL_WORDS to widen):
    #   order brave world phrase find seed picture welcome peace police matter more
    #   one end first future
    OPTIONAL_WORDS= ["order", "brave", "world", "phrase"],

    # Optional 1-based slot locks, applied only when that word is in the current set.
    # e.g. {"moon":10,"tower":1}.  Each lock removes a permutation dimension.
    POSITION_LOCKS= {},

    # BIP39 passphrase ("25th word") candidates. "" = none. Keep this list short;
    # every entry multiplies the work. These come from the image's number inventory.
    PASSPHRASES   = ["", "1865", "2020", "0525", "1103", "05.25.20", "11.03.20",
                     "Tuesday", "BLM", "16", "28", "155", "3885"],

    # Derivation schemes to test (target is a legacy "1..." P2PKH address).
    DERIVATIONS   = ["bip44", "m/0", "m/0h/0"],   # bip44 = m/44'/0'/0'/0/i
    RECEIVE_DEPTH = 5,                            # scan indices 0..RECEIVE_DEPTH-1

    # Discord — status pings and the final result can go to different channels.
    DISCORD_STATUS_WEBHOOK_URL = os.environ.get("DISCORD_STATUS_WEBHOOK_URL", ""),  # start/heartbeat/per-job
    DISCORD_RESULT_WEBHOOK_URL = os.environ.get("DISCORD_RESULT_WEBHOOK_URL", ""),  # only the 🎉 found alert
    DISCORD_WEBHOOK_URL        = os.environ.get("DISCORD_WEBHOOK_URL", ""),         # fallback for both
    SEND_SEED_IN_WEBHOOK = False,   # SECURITY: keep False. If the channel/URL leaks,
                                    # a seed in the message = stolen prize. When False,
                                    # the alert just says "FOUND, grab it from the pod".
    HEARTBEAT_MIN = 30,             # progress ping cadence (minutes)

    # Files (default to /workspace which persists on RunPod network volumes)
    CHECKPOINT_FILE = os.environ.get("CHECKPOINT_FILE", "/workspace/puzzle_checkpoint.json"),
    SOLVED_FILE     = os.environ.get("SOLVED_FILE",     "/workspace/SOLVED.txt"),

    WORKERS   = int(os.environ.get("WORKERS", os.cpu_count() or 1)),
    CHUNK     = 50_000,             # permutations per work unit
)
# ===================================================================

_VALIDATOR = Bip39MnemonicValidator()
_W = {}   # per-worker config (set via pool initializer)


# ----------------------- permutation math -----------------------
def factorial(n): return math.factorial(n)

def unrank(sorted_items, rank):
    """Return the lexicographic permutation of `sorted_items` at position `rank`."""
    items = list(sorted_items); out = []
    for i in range(len(items) - 1, -1, -1):
        f = factorial(i)
        idx, rank = divmod(rank, f)
        out.append(items.pop(idx))
    return out

def next_perm(a):
    """In-place next lexicographic permutation; False if `a` is the last one."""
    n = len(a); i = n - 2
    while i >= 0 and a[i] >= a[i + 1]: i -= 1
    if i < 0: return False
    j = n - 1
    while a[j] <= a[i]: j -= 1
    a[i], a[j] = a[j], a[i]
    a[i + 1:] = reversed(a[i + 1:])
    return True


# ----------------------- derivation -----------------------
def addresses_for_seed(seed, schemes, depth):
    out = []
    if "bip44" in schemes:
        acc = (Bip44.FromSeed(seed, Bip44Coins.BITCOIN)
               .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT))
        for i in range(depth):
            out.append(acc.AddressIndex(i).PublicKey().ToAddress())
    need_root = any(s in schemes for s in ("m", "m/0", "m/0h/0"))
    if need_root:
        root = Bip32Slip10Secp256k1.FromSeed(seed)
        if "m" in schemes:
            out.append(P2PKHAddr.EncodeKey(root.PublicKey().KeyObject()))
        if "m/0" in schemes:
            n0 = root.ChildKey(Bip32KeyIndex(0))
            for i in range(depth):
                out.append(P2PKHAddr.EncodeKey(n0.ChildKey(Bip32KeyIndex(i)).PublicKey().KeyObject()))
        if "m/0h/0" in schemes:
            n0h = root.ChildKey(Bip32KeyIndex.HardenIndex(0)).ChildKey(Bip32KeyIndex(0))
            for i in range(depth):
                out.append(P2PKHAddr.EncodeKey(n0h.ChildKey(Bip32KeyIndex(i)).PublicKey().KeyObject()))
    return out


def check_mnemonic(words):
    """Return (mnemonic, passphrase, scheme_label, addr) on a hit, else None."""
    mn = " ".join(words)
    if not _VALIDATOR.IsValid(mn):              # cheap checksum filter (~15/16 rejected)
        return None
    for pp in _W["PASSPHRASES"]:
        seed = Bip39SeedGenerator(mn).Generate(pp)
        addrs = addresses_for_seed(seed, _W["DERIVATIONS"], _W["RECEIVE_DEPTH"])
        if _W["TARGET"] in addrs:
            return (mn, pp, _W["DERIVATIONS"], addrs.index(_W["TARGET"]))
    return None


# ----------------------- worker -----------------------
def _init(worker_cfg):
    _W.update(worker_cfg)

def _work(item):
    template, free_words, free_slots, start, count = item
    arr = unrank(sorted(free_words), start)
    for _ in range(count):
        row = template[:]
        for slot, w in zip(free_slots, arr):
            row[slot] = w
        hit = check_mnemonic(row)
        if hit:
            return hit
        if not next_perm(arr):
            break
    return None


# ----------------------- notifications -----------------------
def notify(content, cfg, kind="status"):
    """kind='result' -> result webhook; anything else -> status webhook.
    Falls back to DISCORD_WEBHOOK_URL if the specific one isn't set."""
    if kind == "result":
        url = cfg.get("DISCORD_RESULT_WEBHOOK_URL") or cfg.get("DISCORD_WEBHOOK_URL") or ""
    else:
        url = cfg.get("DISCORD_STATUS_WEBHOOK_URL") or cfg.get("DISCORD_WEBHOOK_URL") or ""
    if not url:
        print(f"[webhook:dry-run:{kind}]", content)
        return
    body = json.dumps({"content": content[:1900]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (compatible; puzzle-solver/1.0)"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"[webhook error:{kind}]", e)

def on_found(hit, cfg):
    mn, pp, scheme, idx = hit
    with open(cfg["SOLVED_FILE"], "w") as f:
        f.write(f"address:   {cfg['TARGET']}\nmnemonic:  {mn}\n"
                f"passphrase:{pp!r}\nscheme:    {scheme} (match index {idx})\n"
                f"found:     {datetime.now(timezone.utc).isoformat()}\n")
    if cfg["SEND_SEED_IN_WEBHOOK"]:
        notify(f"🎉 SOLVED {cfg['TARGET']}\nseed: `{mn}`\npassphrase: `{pp}`\nidx {idx}", cfg, kind="result")
    else:
        notify(f"🎉 FOUND {cfg['TARGET']} — seed written to {cfg['SOLVED_FILE']} on the pod. "
               f"Retrieve it NOW (passphrase {'set' if pp else 'none'}, idx {idx}).", cfg, kind="result")
    print("\n*** SOLVED ***  seed:", mn, "| passphrase:", repr(pp), "| idx", idx)


# ----------------------- checkpoint -----------------------
def load_ckpt(path):
    try:
        with open(path) as f: return set(json.load(f).get("done_sets", []))
    except Exception: return set()

def save_ckpt(path, done):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f: json.dump({"done_sets": sorted(done)}, f)
    except Exception as e: print("[checkpoint error]", e)


# ----------------------- main search -----------------------
def build_sets(cfg):
    known = cfg["KNOWN_WORDS"]; need = cfg["SEED_LEN"] - len(known)
    if need < 0:
        sys.exit("KNOWN_WORDS longer than SEED_LEN.")
    pool = [w for w in cfg["OPTIONAL_WORDS"] if w not in known]
    if need > len(pool):
        sys.exit("Not enough OPTIONAL_WORDS to fill the seed.")
    return [tuple(known) + combo for combo in itertools.combinations(pool, need)]

def template_for_set(words, locks):
    n = len(words)
    template = [None] * n
    used = set()
    for w, pos in locks.items():
        if w in words and 1 <= pos <= n and template[pos-1] is None:
            template[pos-1] = w; used.add(w)
    free_words = [w for w in words if w not in used]
    free_slots = [i for i, v in enumerate(template) if v is None]
    return template, free_words, free_slots

def run(cfg):
    sets = build_sets(cfg)
    done = load_ckpt(cfg["CHECKPOINT_FILE"])
    per_set_perms = factorial(cfg["SEED_LEN"] - len(cfg["POSITION_LOCKS"]))  # upper bound
    print(f"[i] target {cfg['TARGET']}")
    print(f"[i] {len(sets)} candidate word-sets x up to {per_set_perms:,} orderings each")
    print(f"[i] passphrases={len(cfg['PASSPHRASES'])}  schemes={cfg['DERIVATIONS']} "
          f"depth={cfg['RECEIVE_DEPTH']}  workers={cfg['WORKERS']}")
    print(f"[i] resuming: {len(done)}/{len(sets)} sets already done\n")
    notify(f"▶️ puzzle solver started: {len(sets)} sets, {len(done)} already done, "
           f"{cfg['WORKERS']} workers.", cfg)

    t0 = time.time(); last_beat = t0; scanned = 0
    pool = mp.Pool(cfg["WORKERS"], initializer=_init, initargs=(cfg,))
    try:
        for si, words in enumerate(sets):
            if si in done:
                continue
            template, free_words, free_slots = template_for_set(words, cfg["POSITION_LOCKS"])
            total = factorial(len(free_words))
            items = [(template, free_words, free_slots, s, min(cfg["CHUNK"], total - s))
                     for s in range(0, total, cfg["CHUNK"])]
            for hit in pool.imap_unordered(_work, items):
                scanned += cfg["CHUNK"]
                if hit:
                    on_found(hit, cfg); pool.terminate(); return hit
                now = time.time()
                if now - last_beat >= cfg["HEARTBEAT_MIN"] * 60:
                    rate = scanned / (now - t0) if now > t0 else 0
                    msg = (f"⏳ {si}/{len(sets)} sets, ~{scanned:,} orderings, "
                           f"{rate:,.0f}/s, {(now-t0)/3600:.1f}h elapsed.")
                    print("  " + msg); notify(msg, cfg); last_beat = now
            done.add(si); save_ckpt(cfg["CHECKPOINT_FILE"], done)
            print(f"  set {si+1}/{len(sets)} done ({words[len(cfg['KNOWN_WORDS']):]}) "
                  f"[{(time.time()-t0)/3600:.2f}h]")
    finally:
        pool.close(); pool.join()

    msg = f"❌ Exhausted all {len(sets)} sets, no match. ({(time.time()-t0)/3600:.1f}h)"
    print("\n" + msg); notify(msg, cfg)
    return None


# ----------------------- self-test -----------------------
def selftest(cfg):
    """Plant a KNOWN seed into a tiny search and confirm the tool finds it AND fires
    the webhook. Validates derivation, ordering, passphrase handling, and Discord."""
    M = "pioneer quick finish actual prevent reject trumpet insect virtual mask cannon creek"
    ADDR_NOPP = "1EHV5ctwGEF4QUBU95uGnDo24Aown3WNrN"
    ADDR_PP   = "1QgxxNZrtKk4V51SUaZxCwRWzgCJ5zbS5"   # same seed, passphrase "test"
    words = M.split()

    print("=== SELF-TEST 1: no passphrase, 10 of 12 positions locked (2 orderings) ===")
    c = dict(cfg)
    c.update(TARGET=ADDR_NOPP, SEED_LEN=12, KNOWN_WORDS=words, OPTIONAL_WORDS=[],
             POSITION_LOCKS={w: i+1 for i, w in enumerate(words[:10])},   # lock first 10
             PASSPHRASES=[""], DERIVATIONS=["bip44"], RECEIVE_DEPTH=1,
             CHECKPOINT_FILE="/tmp/st1.json", SOLVED_FILE="/tmp/st1_SOLVED.txt", WORKERS=2)
    if os.path.exists(c["CHECKPOINT_FILE"]): os.remove(c["CHECKPOINT_FILE"])
    hit = run(c)
    ok1 = hit is not None and hit[0] == M
    print("RESULT 1:", "PASS ✅" if ok1 else "FAIL ❌")

    print("\n=== SELF-TEST 2: passphrase 'test' must be discovered in the list ===")
    c2 = dict(cfg)
    c2.update(TARGET=ADDR_PP, SEED_LEN=12, KNOWN_WORDS=words, OPTIONAL_WORDS=[],
              POSITION_LOCKS={w: i+1 for i, w in enumerate(words[:11])},  # lock 11 -> 1 ordering
              PASSPHRASES=["nope", "test", "xyz"], DERIVATIONS=["bip44"], RECEIVE_DEPTH=1,
              CHECKPOINT_FILE="/tmp/st2.json", SOLVED_FILE="/tmp/st2_SOLVED.txt", WORKERS=2)
    if os.path.exists(c2["CHECKPOINT_FILE"]): os.remove(c2["CHECKPOINT_FILE"])
    hit2 = run(c2)
    ok2 = hit2 is not None and hit2[1] == "test"
    print("RESULT 2:", "PASS ✅" if ok2 else "FAIL ❌")

    print("\n=== Overall:", "ALL PASS ✅ workflow is good" if (ok1 and ok2) else "SOMETHING FAILED ❌", "===")
    if not (cfg["DISCORD_STATUS_WEBHOOK_URL"] or cfg["DISCORD_RESULT_WEBHOOK_URL"] or cfg["DISCORD_WEBHOOK_URL"]):
        print("(No webhook env vars set, so the alerts above were dry-run prints. Set "
              "DISCORD_STATUS_WEBHOOK_URL and DISCORD_RESULT_WEBHOOK_URL and re-run "
              "--selftest: the ▶️/❌ status pings should land in the status channel and "
              "the 🎉 result in the result channel.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--send-seed", action="store_true",
                    help="include the raw seed in the Discord alert (NOT recommended)")
    args = ap.parse_args()
    if args.send_seed:
        CONFIG["SEND_SEED_IN_WEBHOOK"] = True
    if args.selftest:
        selftest(CONFIG)
    else:
        run(CONFIG)
