"""Erzeugt Test-Audiodateien in vielen Formaten (inkl. Duplikaten) mit ffmpeg."""
import os
import subprocess
import sys

import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "samples"
FF = os.environ.get("FFMPEG", "ffmpeg")
SR = 44100


def click_track(bpm, seconds, seed=0):
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    y = np.zeros(n, dtype=np.float32)
    beat = int(SR * 60 / bpm)
    t = np.arange(int(SR * 0.08)) / SR
    kick = (np.sin(2 * np.pi * 60 * t * (1 - t * 4)) * np.exp(-t * 30)).astype(np.float32)
    hat = (rng.standard_normal(int(SR * 0.02)) * np.exp(-np.arange(int(SR * 0.02)) / 150)).astype(np.float32) * 0.3
    for i in range(0, n - len(kick), beat):
        y[i:i + len(kick)] += kick
        h = i + beat // 2
        if h + len(hat) < n:
            y[h:h + len(hat)] += hat
    # leises Pad, damit der Fingerabdruck Inhalt hat
    tt = np.arange(n) / SR
    freq = 220 * (1 + (seed % 5) * 0.12)
    y += 0.15 * np.sin(2 * np.pi * freq * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * tt))
    return (y / max(1e-6, np.abs(y).max()) * 0.8).astype(np.float32)


def write(y, path, codec_args, meta):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [FF, "-hide_banner", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
           "-i", "-"] + codec_args
    for k, v in meta.items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(path)
    subprocess.run(cmd, input=y.tobytes(), check=True)


songs = [
    ("DJ Nova", "Midnight Drive", 124, 40, 1),
    ("Kollektiv Süd", "Sonnenaufgang (Extended Mix)", 128, 42, 2),
    ("Bassline Theory", "Deep Pressure", 174, 38, 3),
    ("Lena & The Groove", "Feel It (feat. Mo)", 118, 36, 4),
]

os.makedirs(OUT, exist_ok=True)
for artist, title, bpm, dur, seed in songs:
    y = click_track(bpm, dur, seed)
    meta = {"artist": artist, "title": title, "album": "MOG Test", "genre": "House", "date": "2024"}
    base = os.path.join(OUT, "Library", artist)
    write(y, os.path.join(base, f"{artist} - {title}.mp3"), ["-c:a", "libmp3lame", "-b:a", "320k"], meta)
    if seed in (1, 2):
        # Duplikat in niedriger Qualität, anderes Verzeichnis
        write(y, os.path.join(OUT, "Downloads", f"{artist} - {title} (copy).mp3"),
              ["-c:a", "libmp3lame", "-b:a", "128k"], meta)
    if seed == 1:
        write(y, os.path.join(OUT, "Lossless", f"{artist} - {title}.flac"), ["-c:a", "flac"], meta)
        # falsch getaggtes Duplikat (nur per Fingerabdruck erkennbar)
        write(y, os.path.join(OUT, "Unsortiert", "track01.wav"), ["-c:a", "pcm_s16le"], {})
    if seed == 3:
        write(y, os.path.join(OUT, "Lossless", f"{artist} - {title}.aiff"), ["-c:a", "pcm_s16be"], meta)
        write(y, os.path.join(OUT, "Misc", f"{artist} - {title}.m4a"), ["-c:a", "aac", "-b:a", "256k"], meta)
    if seed == 4:
        write(y, os.path.join(OUT, "Misc", f"{artist} - {title}.ogg"), ["-c:a", "libvorbis", "-q:a", "6"], meta)
        write(y, os.path.join(OUT, "Misc", f"{artist} - {title}.opus"), ["-c:a", "libopus", "-b:a", "128k"], meta)

# exakte Kopie (byte-identisch)
import shutil
src = os.path.join(OUT, "Library", "DJ Nova", "DJ Nova - Midnight Drive.mp3")
shutil.copy2(src, os.path.join(OUT, "Downloads", "DJ Nova - Midnight Drive.mp3"))
# macOS-Ressourcendatei (muss ignoriert werden)
open(os.path.join(OUT, "Downloads", "._DJ Nova - Midnight Drive.mp3"), "wb").write(b"\x00" * 4096)
print("Samples erzeugt in", OUT)
