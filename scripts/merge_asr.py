"""Merge per-chunk ASR JSONL into one timestamped transcript.

Outputs:
  <prefix>.txt   one segment per line, [HH:MM:SS] text
  <prefix>.jsonl merged segments with float start/end

Usage:
  python merge_asr.py --dir C:\\Voice\\work\\asr_chunks --prefix C:\\Voice\\work\\transcript_raw
"""
import argparse
import glob
import json
import os
import re


def ts(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--no-simplify", action="store_true",
                    help="keep Whisper's original characters (it sometimes emits Traditional)")
    args = ap.parse_args()

    files = glob.glob(os.path.join(args.dir, "chunk*.jsonl"))
    files.sort(key=lambda p: int(re.search(r"chunk(\d+)", os.path.basename(p)).group(1)))
    segs = []
    for p in files:
        if os.path.getsize(p) <= 20:
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("text", "").strip():
                segs.append(d)
    if not segs:
        raise SystemExit("no segments: check asr_chunks output")
    segs.sort(key=lambda d: d["start"])

    merged = []
    for d in segs:
        if merged:
            prev = merged[-1]
            if abs(d["start"] - prev["start"]) < 0.3 and d["text"] == prev["text"]:
                continue
            if d["start"] < prev["start"] - 0.01:
                continue
        merged.append(d)

    if not args.no_simplify:
        try:
            from opencc import OpenCC
            cc = OpenCC("t2s")
            for d in merged:
                d["text"] = cc.convert(d["text"])
        except ImportError:
            print("[warn] opencc not installed; Whisper may leave Traditional characters. "
                  "pip install opencc-python-reimplemented", flush=True)

    with open(args.prefix + ".txt", "w", encoding="utf-8") as f:
        for d in merged:
            f.write(f"[{ts(d['start'])}] {d['text']}\n")
    with open(args.prefix + ".jsonl", "w", encoding="utf-8") as f:
        for d in merged:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    chars = sum(len(d["text"]) for d in merged)
    print(f"files={len(files)} segments={len(merged)} chars={chars} "
          f"span={ts(merged[0]['start'])}..{ts(merged[-1]['end'])}")
    print(f"-> {args.prefix}.txt")


if __name__ == "__main__":
    main()
