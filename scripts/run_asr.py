"""Launch and babysit N ASR workers over a chunk plan.

- restarts a worker that dies while work remains (up to --retries)
- prints completed/total with a real ETA
- returns 0 only when every planned chunk has a non-empty JSONL

Usage:
  python run_asr.py --wav C:\\Voice\\work\\audio16k.wav \
      --plan C:\\Voice\\work\\chunks.json --out-dir C:\\Voice\\work\\asr_chunks \
      --model C:\\Voice\\models\\turbo --workers 3 --threads 5
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def done_count(chunks, out_dir):
    n = 0
    for c in chunks:
        p = os.path.join(out_dir, f"chunk{c['i']:03d}.jsonl")
        if os.path.exists(p) and os.path.getsize(p) > 20:
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8"))
    chunks = plan["chunks"]
    total = len(chunks)
    os.makedirs(args.out_dir, exist_ok=True)
    logs = os.path.join(args.out_dir, "logs")
    os.makedirs(logs, exist_ok=True)

    t0 = time.time()
    fails = {w: 0 for w in range(args.workers)}
    procs = {}
    for w in range(args.workers):
        if not any(c["i"] % args.workers == w for c in chunks):
            continue
        cmd = [sys.executable, os.path.join(HERE, "asr_chunks.py"),
               "--wav", args.wav, "--plan", args.plan, "--out-dir", args.out_dir,
               "--model", args.model, "--worker", str(w), "--workers", str(args.workers),
               "--threads", str(args.threads), "--beam", str(args.beam)]
        log = open(os.path.join(logs, f"w{w}.log"), "w", encoding="utf-8")
        procs[w] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log)
        time.sleep(3)  # stagger model loading / memory spikes

    start_done = done_count(chunks, args.out_dir)
    print(f"[run] chunks={total} already_done={start_done} workers={len(procs)} "
          f"threads={args.threads} beam={args.beam}", flush=True)

    last = 0
    while procs:
        time.sleep(5)
        for w, (p, log) in list(procs.items()):
            rc = p.poll()
            if rc is None:
                continue
            log.close()
            procs.pop(w)
            n = done_count(chunks, args.out_dir)
            print(f"[exit] worker{w} rc={rc} done={n}/{total} elapsed={(time.time()-t0)/60:.1f}min", flush=True)
            still = any(c["i"] % args.workers == w and
                        not (os.path.exists(os.path.join(args.out_dir, f"chunk{c['i']:03d}.jsonl")) and
                             os.path.getsize(os.path.join(args.out_dir, f"chunk{c['i']:03d}.jsonl")) > 20)
                        for c in chunks)
            if still and fails[w] < args.retries:
                fails[w] += 1
                cmd = p.args
                log = open(os.path.join(logs, f"w{w}.try{fails[w]}.log"), "w", encoding="utf-8")
                procs[w] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log)
                print(f"[retry] worker{w} attempt {fails[w]}", flush=True)
                time.sleep(3)

        now = time.time()
        if now - last > 30:
            last = now
            n = done_count(chunks, args.out_dir)
            el = now - t0
            rate = (n - start_done) / el if el > 0 else 0
            eta = (total - n) / rate if rate > 0 else 0
            print(f"[progress] {n}/{total} elapsed={el/60:.1f}min eta={eta/60:.1f}min", flush=True)
            if n >= total:
                break

        if done_count(chunks, args.out_dir) >= total:
            break

    n = done_count(chunks, args.out_dir)
    print(f"[result] {n}/{total} chunks done in {(time.time()-t0)/60:.1f}min", flush=True)
    sys.exit(0 if n >= total else 2)


if __name__ == "__main__":
    main()
