"""Transcribe the chunks assigned to one worker.

Each worker loads the model once and processes every workers-th chunk, so a
3-worker run on a 16-core CPU is the default. Output is one JSONL per chunk,
written atomically; an existing non-empty file means "already done", which
makes the whole run resumable after a crash or reboot.

Usage (normally launched by run_asr.py):
  python asr_chunks.py --wav audio16k.wav --plan chunks.json --out-dir asr_chunks \
      --model C:\\Voice\\models\\turbo --worker 0 --workers 3 --threads 5
"""
import argparse
import json
import os
import time
import wave

import numpy as np


def ts(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--prompt", default="", help="leave empty: prompts leak into the first segment")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    plan = json.load(open(args.plan, encoding="utf-8"))
    chunks = plan["chunks"]
    mine = [c for c in chunks if c["i"] % args.workers == args.worker]

    def out_path(i):
        return os.path.join(args.out_dir, f"chunk{i:03d}.jsonl")

    todo = [c for c in mine if not (os.path.exists(out_path(c["i"])) and os.path.getsize(out_path(c["i"])) > 20)]
    print(f"[w{args.worker}] model={args.model} mine={len(mine)} todo={len(todo)}", flush=True)
    if not todo:
        print(f"[w{args.worker}] nothing to do", flush=True)
        return

    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=args.threads)
    print(f"[w{args.worker}] model loaded in {time.time()-t0:.1f}s", flush=True)

    wf = wave.open(args.wav)
    sr = wf.getframerate()
    for c in todo:
        i, start, end = c["i"], float(c["start"]), float(c["end"])
        wf.setpos(int(start * sr))
        raw = wf.readframes(int((end - start) * sr))
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        t1 = time.time()
        segments, _ = model.transcribe(
            audio,
            language="zh",
            beam_size=args.beam,
            vad_filter=False,
            condition_on_previous_text=False,
            without_timestamps=False,
            temperature=0.0,
            max_new_tokens=200,
            repetition_penalty=1.05,
            no_repeat_ngram_size=4,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            initial_prompt=args.prompt or None,
        )
        tmp = out_path(i) + ".tmp"
        ntext = 0
        with open(tmp, "w", encoding="utf-8") as f:
            for s in segments:
                text = s.text.strip()
                if not text:
                    continue
                ntext += len(text)
                f.write(json.dumps({"start": round(start + s.start, 2),
                                    "end": round(start + s.end, 2),
                                    "text": text}, ensure_ascii=False) + "\n")
        if ntext == 0:
            # Silence / applause still counts as a finished chunk; merge_asr
            # ignores empty text, but run_asr must not retry this chunk forever.
            with open(tmp, "a", encoding="utf-8") as f:
                f.write(json.dumps({"start": start, "end": end, "text": ""},
                                   ensure_ascii=False) + "\n")
        os.replace(tmp, out_path(i))
        dt = time.time() - t1
        print(f"[w{args.worker}] chunk{i:03d} {ts(start)}-{ts(end)} audio={end-start:.0f}s "
              f"took={dt:.1f}s speed={(end-start)/dt:.2f}x chars={ntext}", flush=True)

    wf.close()
    print(f"[w{args.worker}] DONE total={time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
