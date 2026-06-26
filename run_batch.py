#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch runner for the 0.2 BTC puzzle solver.

Reads a list of hypotheses (each = one 12-word search definition) from
hypotheses.json and runs them in sequence. Every job gets its own checkpoint and
SOLVED file under WORKDIR/<label>/, so an interrupted pod resumes exactly where it
left off, and finished jobs are skipped on restart.

Run:
    pip install -r requirements.txt
    export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/XXX/YYY"   # optional
    python3 run_batch.py

Point at a different hypothesis file:
    HYPOTHESES_FILE=my_jobs.json python3 run_batch.py

Persist across disconnects on RunPod:
    nohup python3 run_batch.py > batch.log 2>&1 &
    tail -f batch.log
"""
import json, os, sys, time
import puzzle_solver as ps

HERE    = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.environ.get("WORKDIR", "/workspace")
HYP     = os.environ.get("HYPOTHESES_FILE", os.path.join(HERE, "hypotheses.json"))
BATCH_DONE = os.path.join(WORKDIR, "batch_done.json")


def load_done():
    try:
        with open(BATCH_DONE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_done(done):
    os.makedirs(WORKDIR, exist_ok=True)
    with open(BATCH_DONE, "w") as f:
        json.dump(sorted(done), f)


def main():
    base = dict(ps.CONFIG)
    with open(HYP) as f:
        jobs = json.load(f)

    # sanity-check labels are unique
    labels = [j["label"] for j in jobs]
    if len(labels) != len(set(labels)):
        sys.exit("Duplicate labels in hypotheses file; labels must be unique.")

    done = load_done()
    print(f"[batch] {len(jobs)} hypotheses, {len(done)} already finished, "
          f"workdir={WORKDIR}")
    ps.notify(f"📋 Batch starting: {len(jobs)} hypotheses ({len(done)} already done).", base)

    t0 = time.time()
    for i, job in enumerate(jobs, 1):
        label = job["label"]
        if label in done:
            print(f"[batch] ({i}/{len(jobs)}) skip '{label}' (done)")
            continue

        cfg = dict(base)
        cfg.update(job.get("overrides", {}))
        jobdir = os.path.join(WORKDIR, label)
        os.makedirs(jobdir, exist_ok=True)
        cfg["CHECKPOINT_FILE"] = os.path.join(jobdir, "checkpoint.json")
        cfg["SOLVED_FILE"]     = os.path.join(jobdir, "SOLVED.txt")

        print(f"\n========== ({i}/{len(jobs)}) JOB '{label}' ==========")
        ps.notify(f"🧩 ({i}/{len(jobs)}) job '{label}' starting.", cfg)
        hit = ps.run(cfg)             # run() handles its own found/heartbeat alerts

        if hit:
            print(f"[batch] SOLVED on '{label}' -> {cfg['SOLVED_FILE']}. Stopping batch.")
            return

        done.add(label)
        save_done(done)
        print(f"[batch] '{label}' exhausted, no match. "
              f"[{(time.time()-t0)/3600:.2f}h total]")

    ps.notify(f"🏁 Batch complete: all {len(jobs)} hypotheses exhausted, no match. "
              f"({(time.time()-t0)/3600:.1f}h)", base)
    print("[batch] all hypotheses exhausted, no match.")


if __name__ == "__main__":
    main()
