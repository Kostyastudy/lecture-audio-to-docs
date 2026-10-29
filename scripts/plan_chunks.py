"""Plan ASR chunks, cutting near low-energy points so words are not sliced.

Reads a 16 kHz mono WAV and writes a plan JSON:
  {"duration": 2725.0, "chunks": [{"i":0,"start":0.0,"end":62.3}, ...]}

Defaults are tuned for Chinese lecture audio on CPU: ~60 s chunks, search
+/- 6 s around each target for a 0.3 s quiet window.

Usage:
  python plan_chunks.py --wav C:\\Voice\\work\\audio16k.wav --out C:\\Voice\\work\\chunks.json
"""
import argparse
import json
import wave

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=float, default=60.0, help="target seconds per chunk")
    ap.add_argument("--search", type=float, default=6.0, help="+/- seconds to look for a quiet cut")
    ap.add_argument("--min-len", type=float, default=20.0, help="never emit chunks shorter than this")
    args = ap.parse_args()

    with wave.open(args.wav) as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        data = np.frombuffer(wf.readframes(n), dtype=np.int16)
    dur = n / sr

    targets = []
    t = args.chunk
    while t < dur - args.min_len:
        targets.append(t)
        t += args.chunk

    win = int(0.3 * sr)          # energy window
    cuts = []
    for target in targets:
        lo = max(0.0, target - args.search)
        hi = min(dur, target + args.search)
        a, b = int(lo * sr), int(hi * sr)
        seg = data[a:b].astype(np.float64)
        m = len(seg) // win
        if m < 2:
            cuts.append(target)
            continue
        energies = np.sqrt(np.mean(seg[: m * win].reshape(m, win) ** 2, axis=1))
        best = int(np.argmin(energies))
        cuts.append(round((a + best * win) / sr, 2))

    bounds = [0.0]
    for c in cuts:
        if c - bounds[-1] >= args.min_len and dur - c >= args.min_len:
            bounds.append(c)
    bounds.append(round(dur, 2))
    chunks = [{"i": i, "start": bounds[i], "end": bounds[i + 1]} for i in range(len(bounds) - 1)]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"duration": dur, "chunks": chunks}, f, ensure_ascii=False, indent=1)

    lens = [c["end"] - c["start"] for c in chunks]
    print(f"duration={dur:.1f}s chunks={len(chunks)} avg={sum(lens)/len(lens):.1f}s "
          f"min={min(lens):.1f}s max={max(lens):.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
