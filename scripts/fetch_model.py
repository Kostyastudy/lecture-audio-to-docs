"""Download a faster-whisper model from ModelScope, resumably and in parallel.

HuggingFace is unreliable from this machine (HEAD 308 / TLS resets / slow);
ModelScope holds mirrors of the same CT2 models and sustains ~4 MB/s. Letting
faster-whisper auto-download hangs, so fetch the files first and pass the local
directory as --model.

Default model: pengzhendong/faster-whisper-large-v3-turbo (~1.6 GB, the only
usable choice on this CPU).

Usage:
  python fetch_model.py --dest C:\\Voice\\models\\turbo
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

import requests

CHUNK = 8 * 1024 * 1024
WANT = {"config.json", "preprocessor_config.json", "tokenizer.json",
        "vocabulary.json", "vocabulary.txt", "model.bin"}


def list_files(repo, revision):
    url = f"https://modelscope.cn/api/v1/models/{repo}/repo/files?Revision={revision}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()["Data"]["Files"]
    return {f["Name"]: int(f["Size"]) for f in data if f.get("Type") == "blob"}


def fetch_range(url, start, end, dest, tries=6):
    want = end - start + 1
    for k in range(tries):
        try:
            r = requests.get(url, headers={"Range": f"bytes={start}-{end}"},
                             stream=True, timeout=(20, 120))
            if r.status_code not in (200, 206):
                raise RuntimeError(f"HTTP {r.status_code}")
            buf = bytearray()
            for c in r.iter_content(262144):
                buf.extend(c)
                if len(buf) >= want:
                    break
            if len(buf) != want:
                raise RuntimeError(f"short {len(buf)} != {want}")
            with open(dest, "wb") as f:
                f.write(buf)
            return
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            time.sleep(2 + k * 2)


def download_big(name, size, base, dest, workers):
    chunk_dir = dest + ".chunks"
    os.makedirs(chunk_dir, exist_ok=True)
    n = (size + CHUNK - 1) // CHUNK
    tasks = []
    for i in range(n):
        start = i * CHUNK
        end = min(size, start + CHUNK) - 1
        p = os.path.join(chunk_dir, f"{i:05d}.bin")
        if os.path.exists(p) and os.path.getsize(p) == end - start + 1:
            continue
        tasks.append((start, end, p))
    print(f"[{name}] {size/1048576:.0f}MB chunks={n} todo={len(tasks)}", flush=True)

    t0 = time.time()
    done_bytes = size - sum((min(size, s + CHUNK) - s) for s, e, p in tasks)
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch_range, f"{base}/{name}", s, e, p): (s, e) for s, e, p in tasks}
        for fut in cf.as_completed(futs):
            fut.result()
            s, e = futs[fut]
            done_bytes += e - s + 1
            if done_bytes // (160 * 1024 * 1024) != (done_bytes - (e - s + 1)) // (160 * 1024 * 1024):
                el = time.time() - t0
                print(f"  {done_bytes/1048576:.0f}/{size/1048576:.0f}MB "
                      f"{done_bytes/1048576/max(el,1):.2f}MB/s", flush=True)

    tmp = dest + ".tmp"
    with open(tmp, "wb") as out:
        for i in range(n):
            p = os.path.join(chunk_dir, f"{i:05d}.bin")
            with open(p, "rb") as f:
                out.write(f.read())
    os.replace(tmp, dest)
    for i in range(n):
        os.remove(os.path.join(chunk_dir, f"{i:05d}.bin"))
    os.rmdir(chunk_dir)
    print(f"[{name}] done in {time.time()-t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="pengzhendong/faster-whisper-large-v3-turbo")
    ap.add_argument("--dest", default=r"C:\Voice\models\turbo")
    ap.add_argument("--revision", default="master")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    os.makedirs(args.dest, exist_ok=True)
    marker = os.path.join(args.dest, ".complete")
    if os.path.exists(marker):
        print(f"[skip] {args.dest} already complete")
        return

    try:
        files = list_files(args.repo, args.revision)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"[fatal] ModelScope API failed: {e}")
    wanted = {k: v for k, v in files.items() if k in WANT}
    if "model.bin" not in wanted:
        sys.exit(f"[fatal] model.bin not in repo file list: {sorted(files)}")
    print(f"[repo] {args.repo} files={sorted(wanted)}", flush=True)

    base = f"https://modelscope.cn/models/{args.repo}/resolve/{args.revision}"
    for name, size in sorted(wanted.items()):
        dest = os.path.join(args.dest, name)
        if os.path.exists(dest) and os.path.getsize(dest) == size:
            print(f"[skip] {name}")
            continue
        if size > 100 * 1024 * 1024:
            download_big(name, size, base, dest, args.workers)
        else:
            print(f"[get] {name} {size/1024:.0f}KB", flush=True)
            r = requests.get(f"{base}/{name}", timeout=120)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)

    open(marker, "w").write(json.dumps({"repo": args.repo, "time": time.time()}))
    total = sum(os.path.getsize(os.path.join(args.dest, n)) for n in wanted)
    print(f"[done] {args.dest} {total/1048576:.0f}MB")


if __name__ == "__main__":
    main()
