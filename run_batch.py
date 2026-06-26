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


def parse_selector(n_jobs):
    """JOB_ID env -> set of 1-based job indices to run.
       unset / 0 / all -> every job
       '5'             -> just job 5
       '1-35'          -> a range (great for sharding across pods)
       '1,4,9'         -> a list
       '1-10,20,30-32' -> any combination
    The index N corresponds to the Nth entry in hypotheses.json (label h{N:04d}_...)."""
    raw = os.environ.get("JOB_ID", "0").strip().lower()
    if raw in ("", "0", "all"):
        return set(range(1, n_jobs + 1))
    sel = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            sel.update(range(int(a), int(b) + 1))
        else:
            sel.add(int(part))
    return {i for i in sel if 1 <= i <= n_jobs}


def main():
    base = dict(ps.CONFIG)
    with open(HYP) as f:
        jobs = json.load(f)

    labels = [j["label"] for j in jobs]
    if len(labels) != len(set(labels)):
        sys.exit("Duplicate labels in hypotheses file; labels must be unique.")

    selected = parse_selector(len(jobs))
    if not selected:
        sys.exit(f"JOB_ID={os.environ.get('JOB_ID')!r} selected no jobs (valid: 1..{len(jobs)}).")

    shard = os.environ.get("JOB_ID", "0") or "0"
    print(f"[batch] {len(jobs)} hypotheses total; this pod runs {len(selected)} of them "
          f"(JOB_ID={shard}); workdir={WORKDIR}")
    ps.notify(f"📋 Batch starting (JOB_ID={shard}): running {len(selected)} of "
              f"{len(jobs)} hypotheses.", base)

    t0 = time.time()
    for i, job in enumerate(jobs, 1):
        if i not in selected:
            continue
        label = job["label"]
        jobdir = os.path.join(WORKDIR, label)
        os.makedirs(jobdir, exist_ok=True)
        done_marker = os.path.join(jobdir, "DONE")
        if os.path.exists(done_marker):
            print(f"[batch] ({i}/{len(jobs)}) skip '{label}' (already DONE)")
            continue

        cfg = dict(base)
        cfg.update(job.get("overrides", {}))
        cfg["CHECKPOINT_FILE"] = os.path.join(jobdir, "checkpoint.json")
        cfg["SOLVED_FILE"]     = os.path.join(jobdir, "SOLVED.txt")

        print(f"\n========== ({i}/{len(jobs)}) JOB '{label}' ==========")
        ps.notify(f"🧩 ({i}/{len(jobs)}) job '{label}' starting.", cfg)
        hit = ps.run(cfg)                 # run() emits its own heartbeat/result alerts

        if hit:
            print(f"[batch] SOLVED on '{label}' -> {cfg['SOLVED_FILE']}. Stopping.")
            return

        open(done_marker, "w").close()    # race-free per-job completion marker
        print(f"[batch] '{label}' exhausted, no match. "
              f"[{(time.time()-t0)/3600:.2f}h total]")

    ps.notify(f"🏁 Batch (JOB_ID={shard}) complete: selected hypotheses exhausted, "
              f"no match. ({(time.time()-t0)/3600:.1f}h)", base)
    print("[batch] selected hypotheses exhausted, no match.")


if __name__ == "__main__":
    main()
