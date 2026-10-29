"""Single-process transcription for short audio (< ~15 min) or spot checks.

For anything longer use plan_chunks.py + run_asr.py: this script is ~2x real
time on this CPU and has no resume.

Usage:
  python asr_full.py --wav C:\\Voice\\work\\audio16k.wav \
      --model C:\\Voice\\models\\turbo --out C:\\Voice\\work\\sample
"""
import argparse
import json
import time


def ts(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, help="prefix, no extension")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--prompt", default="")
    args = ap.parse_args()

    import wave
    import numpy as np
    from faster_whisper import WhisperModel

    w = wave.open(args.wav)
    sr = w.getframerate()
    total = w.getnframes()
    end = args.end if args.end is not None else total / sr
    w.setpos(int(args.start * sr))
    raw = w.readframes(int((end - args.start) * sr))
    w.close()
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    t0 = time.time()
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=args.threads)
    print(f"[load] {time.time()-t0:.1f}s", flush=True)
    segments, info = model.transcribe(
        audio,
        language="zh",
        beam_size=args.beam,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
        condition_on_previous_text=False,
        initial_prompt=args.prompt or None,
        word_timestamps=False,
        temperature=0.0,
    )
    print(f"[info] audio={end-args.start:.1f}s lang={info.language}", flush=True)

    with open(args.out + ".jsonl", "w", encoding="utf-8") as f, \
            open(args.out + ".txt", "w", encoding="utf-8") as g:
        for s in segments:
            text = s.text.strip()
            if not text:
                continue
            f.write(json.dumps({"start": round(args.start + s.start, 2),
                                "end": round(args.start + s.end, 2),
                                "text": text}, ensure_ascii=False) + "\n")
            g.write(f"[{ts(args.start + s.start)}] {text}\n")
            f.flush()
            g.flush()
    print(f"[done] {time.time()-t0:.1f}s speed={(end-args.start)/(time.time()-t0):.2f}x", flush=True)


if __name__ == "__main__":
    main()
