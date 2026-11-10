"""Einbindung von ffmpeg: Konvertierung und Dekodierung."""
import os
import re
import subprocess
from dataclasses import dataclass, field

from .fileops import no_window_flags
from .paths import find_tool


def find_ffmpeg(configured=None):
    p = find_tool("ffmpeg", configured)
    if p:
        return p
    try:  # im Build mitgeliefert über imageio-ffmpeg
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_version(exe):
    try:
        out = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True,
                             timeout=10, **no_window_flags()).stdout
        m = re.search(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "unbekannt"
    except Exception:
        return None


@dataclass
class Preset:
    key: str
    name: str
    ext: str
    args: list
    lossless: bool = False
    cover: bool = True       # Format kann ein Cover tragen
    note: str = ""
    sample_formats: list = field(default_factory=list)


PRESETS = [
    Preset("mp3_320", "MP3 · 320 kbps CBR (empfohlen für DJs)", ".mp3",
           ["-c:a", "libmp3lame", "-b:a", "320k"]),
    Preset("mp3_v0", "MP3 · VBR V0 (~245 kbps)", ".mp3", ["-c:a", "libmp3lame", "-q:a", "0"],
           note="VBR kann bei manchen Playern ungenaue Sprungmarken haben."),
    Preset("mp3_256", "MP3 · 256 kbps CBR", ".mp3", ["-c:a", "libmp3lame", "-b:a", "256k"]),
    Preset("mp3_192", "MP3 · 192 kbps CBR", ".mp3", ["-c:a", "libmp3lame", "-b:a", "192k"]),
    Preset("aac_256", "AAC (M4A) · 256 kbps", ".m4a", ["-c:a", "aac", "-b:a", "256k"]),
    Preset("alac", "ALAC (M4A) · verlustfrei", ".m4a", ["-c:a", "alac"], lossless=True),
    Preset("flac", "FLAC · verlustfrei", ".flac", ["-c:a", "flac", "-compression_level", "8"],
           lossless=True),
    Preset("wav16", "WAV · 16 Bit PCM", ".wav", ["-c:a", "pcm_s16le"], lossless=True),
    Preset("wav24", "WAV · 24 Bit PCM", ".wav", ["-c:a", "pcm_s24le"], lossless=True),
    Preset("aiff16", "AIFF · 16 Bit PCM", ".aiff", ["-c:a", "pcm_s16be"], lossless=True),
    Preset("aiff24", "AIFF · 24 Bit PCM", ".aiff", ["-c:a", "pcm_s24be"], lossless=True),
    Preset("ogg_q8", "Ogg Vorbis · Qualität 8 (~256 kbps)", ".ogg", ["-c:a", "libvorbis", "-q:a", "8"]),
    Preset("opus_192", "Opus · 192 kbps", ".opus", ["-c:a", "libopus", "-b:a", "192k"]),
]
PRESETS_BY_KEY = {p.key: p for p in PRESETS}


class EncoderError(Exception):
    pass


def build_command(ffmpeg, src, dst, preset, samplerate=None, channels=None):
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", src,
           "-map", "0:a:0", "-map_metadata", "-1", "-vn"]
    cmd += preset.args
    if samplerate:
        cmd += ["-ar", str(samplerate)]
    if channels:
        cmd += ["-ac", str(channels)]
    if preset.ext == ".mp3":
        cmd += ["-id3v2_version", "3", "-write_xing", "1"]
    if preset.ext == ".opus" and samplerate and samplerate not in (48000, 24000, 16000, 12000, 8000):
        cmd[cmd.index("-ar") + 1] = "48000"
    cmd += ["-progress", "pipe:1", "-nostats", dst]
    return cmd


def convert(ffmpeg, src, dst, preset, duration=0.0, samplerate=None, channels=None,
            progress=None, cancel=None):
    """Konvertiert src nach dst. progress(0..1). Wirft EncoderError."""
    tmp = dst + ".mogtmp" + preset.ext
    cmd = build_command(ffmpeg, src, tmp, preset, samplerate, channels)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", **no_window_flags())
    err_lines = []
    import threading

    def _read_err():
        for line in proc.stderr:
            err_lines.append(line)
            if len(err_lines) > 60:
                del err_lines[:20]
    t = threading.Thread(target=_read_err, daemon=True)
    t.start()
    try:
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.kill()
                break
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    us = int(line.split("=", 1)[1])
                    if duration and progress:
                        progress(min(1.0, us / 1e6 / duration))
                except ValueError:
                    pass
        proc.wait()
        t.join(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()
    if cancel is not None and cancel.is_set():
        _silent_remove(tmp)
        raise EncoderError("Abgebrochen")
    if proc.returncode != 0:
        _silent_remove(tmp)
        msg = "".join(err_lines[-6:]).strip() or f"ffmpeg Fehlercode {proc.returncode}"
        raise EncoderError(msg)
    os.replace(tmp, dst)
    if progress:
        progress(1.0)
    return dst


def _silent_remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def decode_mono(ffmpeg, path, samplerate=11025, start=0.0, length=None):
    """Dekodiert Audio zu Mono-float32 (numpy-Array)."""
    import numpy as np
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.2f}"]
    cmd += ["-i", path]
    if length:
        cmd += ["-t", f"{length:.2f}"]
    cmd += ["-map", "0:a:0", "-ac", "1", "-ar", str(samplerate), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=300, **no_window_flags())
    if p.returncode != 0 and not p.stdout:
        raise EncoderError(p.stderr.decode("utf-8", "replace").strip()[-400:] or "Dekodierung fehlgeschlagen")
    return np.frombuffer(p.stdout, dtype=np.float32)


def target_path(src, preset, out_dir=None, keep_structure_from=None):
    stem = os.path.splitext(os.path.basename(src))[0]
    if out_dir:
        if keep_structure_from:
            rel = os.path.relpath(os.path.dirname(src), keep_structure_from)
            if rel.startswith(".."):
                rel = ""
            d = os.path.join(out_dir, rel)
        else:
            d = out_dir
    else:
        d = os.path.dirname(src)
    return os.path.join(d, stem + preset.ext)


def unique_path(p):
    if not os.path.exists(p):
        return p
    stem, ext = os.path.splitext(p)
    i = 2
    while os.path.exists(f"{stem} ({i}){ext}"):
        i += 1
    return f"{stem} ({i}){ext}"
