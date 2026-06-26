# BTC Puzzle Solver (0.2 BTC seed-phrase puzzle)

Tooling for the "0.2 BTC" BIP39 seed-phrase puzzle whose prize address is
`1KfZGvwZxsvSmemoCmEV75uqcNzYBHjkHZ`. The puzzle hides a 12-word seed across an
image; this searches orderings/subsets of the candidate words read off that image.

This is a search over a **fixed, small candidate word pool** — not a wallet
brute-forcer. A random 12-word BIP39 seed has 2^128 entropy and is uncrackable;
this is only finite because the puzzle deliberately constrains the words.

## What's here

- `puzzle_solver.py` — the engine. Picks the unknown words from a pool, tries every
  BIP39-checksum-valid ordering, across several derivation paths and a passphrase
  list. Has multiprocessing, checkpoint/resume, a Discord webhook, and a self-test.
- `run_batch.py` — runs many 12-word hypotheses in sequence, each independently
  checkpointed.
- `hypotheses.json` — the list of hypotheses the batch runner consumes (edit this).
- `.env.example` — template for the webhook URL and options.

## Install

```bash
pip install -r requirements.txt
```

## Configure the Discord webhook (optional but recommended)

Create a webhook in Discord (Server Settings → Integrations → Webhooks → New
Webhook) pointed at a **private** channel, then either:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/XXX/YYY"
```

or copy `.env.example` to `.env`, fill it in, and `set -a; source .env; set +a`.

**Never commit the real URL.** `.env` is gitignored; the alert on success does not
include the seed by default (see Security below).

## 1) Validate the workflow first

```bash
python3 puzzle_solver.py --selftest
```

This plants a known seed into a tiny search and confirms derivation, ordering,
passphrase discovery, the SOLVED file, and (if the webhook is set) Discord delivery.
You should see `ALL PASS`.

## 2) Run a single hypothesis

Edit the `CONFIG` block at the top of `puzzle_solver.py` (`KNOWN_WORDS`,
`OPTIONAL_WORDS`, `POSITION_LOCKS`, `PASSPHRASES`, `DERIVATIONS`), then:

```bash
python3 puzzle_solver.py
```

## 3) Run a batch of hypotheses

Edit `hypotheses.json` (each entry is one search), then:

```bash
nohup python3 run_batch.py > batch.log 2>&1 &
tail -f batch.log
```

Each job writes to `WORKDIR/<label>/` (default `WORKDIR=/workspace`). Re-running the
batch skips finished jobs and resumes an interrupted one from its checkpoint.

## Running on RunPod

- Use a **high-vCPU CPU pod** (32–64 vCPU) — this engine is CPU-multiprocess, so a
  GPU pod just means paying for an idle GPU. Attach a **network volume mounted at
  `/workspace`** so checkpoints and `SOLVED.txt` survive interruptions.
- Then:
  ```bash
  pip install -r requirements.txt
  export DISCORD_WEBHOOK_URL="..."
  python3 puzzle_solver.py --selftest        # confirm everything, incl. Discord
  nohup python3 run_batch.py > batch.log 2>&1 &
  tail -f batch.log
  ```
- On a hit: Discord pings you and the seed is in `/workspace/<label>/SOLVED.txt`.
  Retrieve it immediately.

## Feasibility / scope

- One **exact 12-word** hypothesis (pool of 4 → choose 4 → 1 set) sweeps all
  passphrases/paths in roughly tens of minutes to a couple hours on a big pod. The
  batch runner is built for queuing many of these.
- A broad **"pick 4 from 16"** sweep is ~1,820 sets × 12! × passphrases ≈ months of
  CPU. That scale needs a CUDA BIP39 kernel (the bottleneck is PBKDF2-HMAC-SHA512
  ×2048); there is no turnkey GPU tool for "subset + anagram + passphrase."

## Security

- `SEND_SEED_IN_WEBHOOK = False` by default: the success alert says a seed was found
  and where it is, but does **not** put the seed in Discord, so a leaked webhook
  can't drain the wallet. The seed is written only to the local `SOLVED.txt`.
- Keep the webhook URL out of git. Regenerate it if it's ever exposed.

## Disclaimer

Educational use against a public prize puzzle whose creator funded the address for
whoever solves it. Don't point key-search tooling at addresses that aren't yours.
