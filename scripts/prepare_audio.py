"""Probe an audio file and convert it to 16 kHz mono PCM WAV.

Primary path: PyAV (no external ffmpeg needed).
Fallback: the ffmpeg binary bundled with imageio-ffmpeg, for MP3s whose
LAME header PyAV refuses to decode.

Usage:
  python prepare_audio.py --src "C:\\path\\talk.mp3" --dst "C:\\Voice\\work\\audio16k.wav"
"""
import argparse
import os
import subprocess
import sys
import wave

import numpy as np


def probe(src):
    import av
    container = av.open(src)
    stream = container.streams.audio[0]
    duration = None
    if stream.duration is not None:
        duration = float(stream.duration * stream.time_base)
    elif container.duration is not None:
        duration = container.duration / 1_000_000
    info = {
        "duration_s": duration,
        "codec": stream.codec_context.name,
        "rate": stream.rate,
        "channels": stream.channels,
    }
    container.close()
    return info


def via_av(src, dst):
    import av
    container = av.open(src)
    stream = container.streams.audio[0]
    res = av.AudioResampler(format="s16", layout="mono", rate=16000)
    total = 0
    with wave.open(dst, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        for frame in container.decode(stream):
            for rf in res.resample(frame):
                arr = rf.to_ndarray()
                if arr.ndim > 1:
                    arr = arr.reshape(-1)
                wf.writeframes(arr.astype(np.int16).tobytes())
                total += len(arr)
        for rf in res.resample(None):
            arr = rf.to_ndarray().reshape(-1)
            wf.writeframes(arr.astype(np.int16).tobytes())
            total += len(arr)
    container.close()
    return total


def via_ffmpeg(src, dst):
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    with wave.open(dst) as wf:
        return wf.getnframes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        sys.exit(f"MISSING input: {args.src}")
    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)

    info = probe(args.src)
    print(f"[probe] {info}", flush=True)
    if os.path.exists(args.dst) and not args.force:
        with wave.open(args.dst) as wf:
            sec = wf.getnframes() / wf.getframerate()
        print(f"[skip] {args.dst} already exists ({sec:.1f}s); use --force to redo")
        return

    try:
        total = via_av(args.src, args.dst)
        how = "pyav"
    except Exception as e:  # noqa: BLE001
        print(f"[pyav failed] {type(e).__name__}: {e}", flush=True)
        try:
            total = via_ffmpeg(args.src, args.dst)
            how = "ffmpeg(imageio-ffmpeg)"
        except Exception as e2:  # noqa: BLE001
            sys.exit(f"[fatal] conversion failed: {e2}")

    sec = total / 16000
    mb = os.path.getsize(args.dst) / 1024 / 1024
    print(f"[done] {how} samples={total} duration={sec:.1f}s = {sec/60:.1f}min size={mb:.0f}MB -> {args.dst}")


if __name__ == "__main__":
    main()
