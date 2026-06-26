# CLAUDE.md

Project context for Claude Code. Keep this file concise and current.

## What this is
Tooling for the "0.2 BTC" BIP39 seed-phrase puzzle (prize address
`1KfZGvwZxsvSmemoCmEV75uqcNzYBHjkHZ`). It searches orderings/subsets of a **fixed,
small candidate word pool** read off the puzzle image. It is NOT a general wallet
brute-forcer — a random 12-word seed is 2^128 and uncrackable; this is finite only
because the word pool is constrained. Work against this public prize puzzle only.

## Files
- `puzzle_solver.py` — engine. Picks unknown words from a pool, tries every
  BIP39-checksum-valid ordering across derivation paths + a passphrase list.
  Multiprocessing, checkpoint/resume, Discord webhooks, and a `--selftest`.
- `run_batch.py` — runs many hypotheses from `hypotheses.json`; `JOB_ID` shards
  across pods; per-job `DONE` markers under `WORKDIR/<label>/`.
- `gen_hypotheses.py` — generates `hypotheses.json` (8 strong words + every
  combination of the optional pool, priority-sorted).
- `bootstrap.py` — pod entrypoint; `FIRST_PASS` toggles a fast no-passphrase /
  BIP44-only sweep, then calls `run_batch.main()`.

## Commands
- Install: `pip install -r requirements.txt`
- Validate everything (do this after ANY change to derivation or webhooks):
  `python3 puzzle_solver.py --selftest`   → must print `ALL PASS`
- Single hypothesis: edit `CONFIG` in `puzzle_solver.py`, then `python3 puzzle_solver.py`
- Batch: `python3 run_batch.py`
- Regenerate queue: `python3 gen_hypotheses.py [--pool-size N] [--max M]`

## Environment variables
- `DISCORD_STATUS_WEBHOOK_URL` — start/heartbeat/per-job pings
- `DISCORD_RESULT_WEBHOOK_URL` — only the 🎉 found alert
- `FIRST_PASS` (default 1) — 1: no passphrase + BIP44 only; 0: full sweep
- `JOB_ID` (default 0/all) — `7`, `1-35`, `1,4,9`, or combos; selects hypotheses
- `WORKERS` (default all cores), `WORKDIR` (default `/workspace`)

## Conventions (important)
- Commits are authored as **lerasah <sachethana@gmail.com>**. Do NOT add a
  "Co-Authored-By: Claude" trailer or any AI attribution (also enforced via
  `.claude/settings.json` → `includeCoAuthoredBy: false`).
- NEVER commit secrets. Webhook URLs live only in env / `.env` (gitignored).
- Keep `SEND_SEED_IN_WEBHOOK = False` — the result alert must not contain the seed.
- The self-test plants a known seed + address; never weaken it.

## Domain facts
- 12-word BIP39 seed; target is a legacy P2PKH ("1...") address.
- Throughput bottleneck is BIP39 PBKDF2-HMAC-SHA512 (2048 iters), run once per
  (mnemonic, passphrase). This is why CPU caps ~2k/s/core with bip_utils.
- The biggest lever is shrinking the search space (word set / order / passphrase),
  not raw speed.

## Open tasks / next steps
1. **CPU speedup:** add an optional faster derivation backend using `coincurve`
   (libsecp256k1) + `hashlib.pbkdf2_hmac`, behind a flag, keeping `bip_utils` as the
   correct reference. Must still pass `--selftest` (identical addresses).
2. **GPU (later):** sketch a CUDA BIP39→BIP44→P2PKH kernel + host harness for the
   broad "pick k from pool" sweep; no turnkey tool exists for subset+anagram+passphrase.
3. Keep `hypotheses.json` prioritized; expand the optional pool only when warranted.

## Workflow
Explore → plan → confirm with the user → implement → run `--selftest` → commit.
Prefer minimal, targeted changes. Ask before large refactors.
