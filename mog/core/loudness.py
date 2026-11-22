"""Lautheit messen (EBU R128) und Lautstärke angleichen.

Messung: ffmpeg-Filter ``ebur128`` – integrierte Lautheit (LUFS), True Peak (dBTP), Dynamik (LRA).

Angleichen – je Format der schonendste Weg:
  MP3         verlustfrei: „global_gain“ jedes Granulats ändern (Prinzip mp3gain), Schritte à 1,5 dB,
              Datei wird an Ort und Stelle geändert (gleiche Größe, Cue-Punkte bleiben gültig)
  WAV / AIFF  Samples direkt in der Datei skalieren, alle anderen Chunks (Tags, Cues) bleiben unberührt
  FLAC / ALAC neu kodiert (verlustfrei), alle Tags und Cover werden übernommen
  Opus        verlustfrei über den „Output Gain“ im Opus-Kopf
  AAC, OGG, WMA … nur durch Neukodierung (Qualitätsverlust) – muss ausdrücklich erlaubt werden
Alternativ: nur ReplayGain-Tags schreiben (Datei bleibt unverändert).
"""
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile

from .fileops import no_window_flags

MP3_STEP = 1.5                      # dB je global_gain-Schritt
REPLAYGAIN_REF = -18.0              # LUFS (ReplayGain 2.0)
R128_REF = -23.0                    # LUFS (Opus R128_TRACK_GAIN)

# Methoden
M_MP3 = "mp3"
M_PCM = "pcm"
M_FLAC = "flac"
M_ALAC = "alac"
M_OPUS = "opus"
M_REENCODE = "reencode"
M_NONE = "none"

METHOD_LABEL = {
    M_MP3: "MP3 verlustfrei (1,5-dB-Schritte)",
    M_PCM: "direkt in der Datei",
    M_FLAC: "FLAC verlustfrei neu kodiert",
    M_ALAC: "ALAC verlustfrei neu kodiert",
    M_OPUS: "Opus-Kopf (verlustfrei)",
    M_REENCODE: "Neukodierung (verlustbehaftet)",
    M_NONE: "nicht möglich",
}
LOSSLESS_METHODS = {M_MP3, M_PCM, M_FLAC, M_ALAC, M_OPUS}

# Neukodierung verlustbehafteter Formate: ffmpeg-Encoder je Format
_REENCODE = {"AAC": "aac", "OGG": "libvorbis", "WMA": "wmav2"}


class LoudnessError(Exception):
    pass


# ==========================================================================
# Messen
# ==========================================================================
_RE_I = re.compile(r"^\s*I:\s*(-?[\d.]+|-inf)\s*LUFS", re.M)
_RE_LRA = re.compile(r"^\s*LRA:\s*(-?[\d.]+)\s*LU", re.M)
_RE_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", re.M)


def measure(ffmpeg, path, timeout=900):
    """Gibt (lufs, true_peak_dbtp, lra) zurück. Wirft LoudnessError."""
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", path, "-map", "0:a:0",
           "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, **no_window_flags())
    except subprocess.TimeoutExpired as e:
        raise LoudnessError("Zeitüberschreitung bei der Messung") from e
    err = p.stderr.decode("utf-8", "replace")
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    mi, mp = _RE_I.search(summary), _RE_PEAK.search(summary)
    if not mi or not mp:
        raise LoudnessError(err.strip().splitlines()[-1][:300] if err.strip() else "Messung fehlgeschlagen")
    lufs = float(mi.group(1)) if mi.group(1) != "-inf" else -70.0
    peak = float(mp.group(1)) if mp.group(1) != "-inf" else -70.0
    ml = _RE_LRA.search(summary)
    return lufs, peak, float(ml.group(1)) if ml else 0.0


# ==========================================================================
# Planen
# ==========================================================================
def method_for(fmt, allow_reencode=False):
    fmt = (fmt or "").upper()
    if fmt == "MP3":
        return M_MP3
    if fmt in ("WAV", "AIFF"):
        return M_PCM
    if fmt == "FLAC":
        return M_FLAC
    if fmt == "ALAC":
        return M_ALAC
    if fmt == "OPUS":
        return M_OPUS
    if fmt in _REENCODE:
        return M_REENCODE if allow_reencode else M_NONE
    return M_NONE


def auto_target(measurements, ceiling=-1.0, share=0.9, lo=-23.0, hi=-6.0):
    """„Optimaler“ Zielpegel: so laut, dass ``share`` der Titel ihn ohne Überschreiten der
    Peak-Grenze erreichen. measurements: Liste von (lufs, peak)."""
    reach = sorted(lufs + (ceiling - peak) for lufs, peak in measurements if lufs is not None and lufs > -60)
    if not reach:
        return -14.0
    idx = max(0, min(len(reach) - 1, int(math.floor((1.0 - share) * len(reach)))))
    return round(max(lo, min(hi, reach[idx])), 1)


def plan_gain(lufs, peak, target, ceiling=-1.0, method=M_PCM, only_down=False):
    """Berechnet die anzuwendende Änderung in dB. Gibt (gain, hinweis) zurück;
    hinweis: "" | "peak" (durch Peak-Grenze begrenzt) | "down" (nur leiser) | "step" (MP3-Raster)."""
    want = target - lufs
    note = ""
    gain = want
    if gain > ceiling - peak:
        gain = ceiling - peak
        note = "peak"
    if only_down and gain > 0:
        gain, note = 0.0, "down"
    if method == M_MP3:
        steps = int(round(gain / MP3_STEP))
        if steps * MP3_STEP > ceiling - peak + 1e-9 and steps > 0:
            steps -= 1
        g = steps * MP3_STEP
        if not note and abs(g - want) > 0.05:
            note = "step"
        gain = g
    elif method == M_OPUS:
        gain = round(gain * 256) / 256
    else:
        gain = round(gain, 2)
    if abs(gain) < 0.05:
        gain = 0.0
    return gain, note


# ==========================================================================
# Anwenden
# ==========================================================================
def apply_gain(ffmpeg, path, fmt, gain_db, allow_reencode=False, bitrate=0):
    """Ändert den Pegel der Datei um gain_db. Gibt die tatsächlich angewendete Änderung (dB) zurück."""
    if not gain_db:
        return 0.0
    m = method_for(fmt, allow_reencode)
    if m == M_MP3:
        steps = int(round(gain_db / MP3_STEP))
        if not steps:
            return 0.0
        mp3_apply_steps(path, steps)
        return steps * MP3_STEP
    if m == M_PCM:
        pcm_scale(path, 10 ** (gain_db / 20.0))
        return gain_db
    if m == M_OPUS:
        return opus_add_gain(path, gain_db)
    if m in (M_FLAC, M_ALAC, M_REENCODE):
        _ffmpeg_reencode(ffmpeg, path, fmt, gain_db, bitrate)
        return gain_db
    raise LoudnessError(f"Für {fmt} ist keine Pegeländerung möglich.")


def _overwrite_contents(src_tmp, dst):
    """Schreibt den Inhalt von src_tmp in die bestehende Datei dst (gleiche Datei bleibt erhalten –
    Erstellungsdatum und Verknüpfungen z. B. in rekordbox bleiben gültig)."""
    with open(src_tmp, "rb") as fi, open(dst, "r+b") as fo:
        shutil.copyfileobj(fi, fo, 4 * 1024 * 1024)
        fo.truncate()
        fo.flush()
        os.fsync(fo.fileno())


# --------------------------------------------------------------------------
# MP3: global_gain (verlustfrei)
# --------------------------------------------------------------------------
_BR_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_BR_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3_header(b, i):
    """Prüft einen Layer-III-Frame-Kopf ab Position i. Gibt (länge, version, mono, crc, sr) oder None."""
    if b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0:
        return None
    ver = (b[i + 1] >> 3) & 3
    layer = (b[i + 1] >> 1) & 3
    if ver == 1 or layer != 1:              # reserviert / nicht Layer III
        return None
    crc = not (b[i + 1] & 1)
    bri = b[i + 2] >> 4
    sri = (b[i + 2] >> 2) & 3
    if bri in (0, 15) or sri == 3:          # freies Format / ungültig
        return None
    pad = (b[i + 2] >> 1) & 1
    mono = (b[i + 3] >> 6) == 3
    sr = _SR[ver][sri]
    if ver == 3:
        length = 144000 * _BR_V1[bri] // sr + pad
    else:
        length = 72000 * _BR_V2[bri] // sr + pad
    return length, ver, mono, crc, sr


def _get_bits(b, pos, n):
    v = 0
    for k in range(n):
        byte = b[(pos + k) >> 3]
        v = (v << 1) | ((byte >> (7 - ((pos + k) & 7))) & 1)
    return v


def _set_bits(b, pos, n, value):
    for k in range(n):
        bit = (value >> (n - 1 - k)) & 1
        idx = (pos + k) >> 3
        sh = 7 - ((pos + k) & 7)
        b[idx] = (b[idx] & ~(1 << sh) & 0xFF) | (bit << sh)


def _crc16(data, crc=0xFFFF):
    for byte in data:
        for k in range(8):
            bit = (byte >> (7 - k)) & 1
            top = (crc >> 15) & 1
            crc = (crc << 1) & 0xFFFF
            if top ^ bit:
                crc ^= 0x8005
    return crc


def _audio_range(b):
    start = 0
    if b[:3] == b"ID3" and len(b) >= 10:
        size = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
        start = 10 + size + (10 if b[5] & 0x10 else 0)
    end = len(b)
    if end - start > 128 and b[end - 128:end - 125] == b"TAG":
        end -= 128
    if end - start > 32 and b[end - 32:end - 24] == b"APETAGEX":
        size = struct.unpack("<I", b[end - 20:end - 16])[0]
        flags = struct.unpack("<I", b[end - 12:end - 8])[0]
        end -= size + (32 if flags & 0x80000000 else 0)
    return start, max(start, end)


def _side_info_layout(ver, mono):
    """(side-info-Bytes, Startbit des 1. global_gain, Bits je Block, Anzahl Blöcke)."""
    nch = 1 if mono else 2
    if ver == 3:
        start = 9 + (5 if mono else 3) + 4 * nch
        return (17 if mono else 32), start, 59, 2 * nch
    start = 8 + (1 if mono else 2)
    return (9 if mono else 17), start, 63, nch


def mp3_scan(b):
    """Liefert die Positionen aller Audio-Frames (ohne Xing/Info/VBRI-Kopf)."""
    start, end = _audio_range(b)
    frames = []
    lock = None
    i = start
    while i + 4 <= end:
        h = _mp3_header(b, i)
        if h is None or (lock and (h[1], h[4]) != lock):
            i += 1
            continue
        length = h[0]
        if i + length > end:
            break
        if lock is None:
            # Erst sperren, wenn der nächste Frame direkt anschließt (gegen Falsch-Sync in Daten)
            nxt = _mp3_header(b, i + length) if i + length + 4 <= end else None
            if nxt is None or (nxt[1], nxt[4]) != (h[1], h[4]):
                if i + length < end - 4:
                    i += 1
                    continue
            lock = (h[1], h[4])
        frames.append((i, h))
        i += length
    # Xing/Info/VBRI-Frame (Kopf ohne Audio) überspringen
    if frames:
        i, h = frames[0]
        side = _side_info_layout(h[1], h[2])[0]
        o = i + 4 + (2 if h[3] else 0) + side
        if b[o:o + 4] in (b"Xing", b"Info") or b[i + 36:i + 40] == b"VBRI":
            frames = frames[1:]
    return frames


def mp3_apply_steps(path, steps):
    """Ändert global_gain aller Granulate um ``steps`` (1 Schritt = 1,5 dB). Gibt (frames, begrenzt) zurück."""
    with open(path, "rb") as f:
        b = bytearray(f.read())
    frames = mp3_scan(b)
    if not frames:
        raise LoudnessError("Keine MP3-Frames gefunden.")
    clipped = 0
    for i, (length, ver, mono, crc, _sr) in frames:
        side_bytes, start, block, nblocks = _side_info_layout(ver, mono)
        base = (i + 4 + (2 if crc else 0)) * 8
        for k in range(nblocks):
            pos = base + start + k * block + 21
            g = _get_bits(b, pos, 8)
            ng = g + steps
            if ng < 0 or ng > 255:
                clipped += 1
                ng = max(0, min(255, ng))
            if ng != g:
                _set_bits(b, pos, 8, ng)
        if crc:
            si = i + 6
            c = _crc16(bytes(b[i + 2:i + 4]) + bytes(b[si:si + side_bytes]))
            b[i + 4] = c >> 8
            b[i + 5] = c & 0xFF
    with open(path, "r+b") as f:
        f.write(b)
        f.flush()
        os.fsync(f.fileno())
    return len(frames), clipped


def mp3_gain_values(path, limit=None):
    """Für Tests: Liste der global_gain-Werte."""
    with open(path, "rb") as f:
        b = bytearray(f.read())
    out = []
    for i, (length, ver, mono, crc, _sr) in mp3_scan(b)[:limit]:
        _side, start, block, nblocks = _side_info_layout(ver, mono)
        base = (i + 4 + (2 if crc else 0)) * 8
        out += [_get_bits(b, base + start + k * block + 21, 8) for k in range(nblocks)]
    return out


# --------------------------------------------------------------------------
# WAV / AIFF: Samples direkt skalieren
# --------------------------------------------------------------------------
def _wav_layout(f):
    hdr = f.read(12)
    if hdr[:4] != b"RIFF" or hdr[8:12] != b"WAVE":
        raise LoudnessError("Keine RIFF/WAVE-Datei (RF64 wird nicht unterstützt).")
    fmt = data = None
    while True:
        ch = f.read(8)
        if len(ch) < 8:
            break
        cid, size = ch[:4], struct.unpack("<I", ch[4:])[0]
        pos = f.tell()
        if cid == b"fmt ":
            raw = f.read(min(size, 40))
            tag, nch, _sr, _br, align, bits = struct.unpack("<HHIIHH", raw[:16])
            if tag == 0xFFFE and len(raw) >= 26:
                tag = struct.unpack("<H", raw[24:26])[0]
            fmt = (tag, nch, align, bits)
        elif cid == b"data":
            data = (pos, size)
        f.seek(pos + size + (size & 1))
    if not fmt or not data:
        raise LoudnessError("WAV-Datei ohne fmt- oder data-Chunk.")
    tag, nch, align, bits = fmt
    if tag == 1:
        kind = {8: "u8", 16: "<i2", 24: "<i3", 32: "<i4"}.get(bits)
    elif tag == 3:
        kind = {32: "<f4", 64: "<f8"}.get(bits)
    else:
        kind = None
    if not kind:
        raise LoudnessError(f"WAV-Kodierung wird nicht unterstützt (Format {tag}, {bits} Bit).")
    return data[0], data[1], kind, align


def _ext80(b):
    exp = ((b[0] & 0x7F) << 8) | b[1]
    mant = int.from_bytes(b[2:10], "big")
    return mant * 2.0 ** (exp - 16383 - 63) if mant else 0.0


def _aiff_layout(f):
    hdr = f.read(12)
    if hdr[:4] != b"FORM" or hdr[8:12] not in (b"AIFF", b"AIFC"):
        raise LoudnessError("Keine AIFF-Datei.")
    aifc = hdr[8:12] == b"AIFC"
    comm = ssnd = None
    while True:
        ch = f.read(8)
        if len(ch) < 8:
            break
        cid, size = ch[:4], struct.unpack(">I", ch[4:])[0]
        pos = f.tell()
        if cid == b"COMM":
            raw = f.read(min(size, 26))
            nch, _nframes, bits = struct.unpack(">hIh", raw[:8])
            comp = raw[18:22] if aifc and len(raw) >= 22 else b"NONE"
            comm = (nch, bits, comp)
        elif cid == b"SSND":
            offset = struct.unpack(">I", f.read(4))[0]
            ssnd = (pos + 8 + offset, size - 8 - offset)
        f.seek(pos + size + (size & 1))
    if not comm or not ssnd:
        raise LoudnessError("AIFF-Datei ohne COMM- oder SSND-Chunk.")
    nch, bits, comp = comm
    comp = comp.lower()
    if comp in (b"none", b"twos"):
        kind = {8: "i1", 16: ">i2", 24: ">i3", 32: ">i4"}.get(bits)
    elif comp == b"sowt":
        kind = {16: "<i2", 24: "<i3", 32: "<i4"}.get(bits)
    elif comp == b"fl32":
        kind = ">f4"
    elif comp == b"fl64":
        kind = ">f8"
    else:
        kind = None
    if not kind:
        raise LoudnessError(f"AIFF-Kodierung „{comp.decode('latin-1')}“ wird nicht unterstützt.")
    width = int(kind[-1]) if kind[-1].isdigit() else 1
    return ssnd[0], ssnd[1], kind, width * nch


def _scale_block(raw, kind, factor):
    import numpy as np
    if kind in ("<i3", ">i3"):
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        if kind == "<i3":
            v = a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16)
        else:
            v = (a[:, 0] << 16) | (a[:, 1] << 8) | a[:, 2]
        v = np.where(v & 0x800000, v - 0x1000000, v).astype(np.float64)
        v = np.clip(np.rint(v * factor), -8388608, 8388607).astype(np.int32)
        out = np.empty((len(v), 3), dtype=np.uint8)
        if kind == "<i3":
            out[:, 0], out[:, 1], out[:, 2] = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
        else:
            out[:, 2], out[:, 1], out[:, 0] = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
        return out.tobytes()
    if kind == "u8":
        v = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128
        return (np.clip(np.rint(v * factor), -128, 127) + 128).astype(np.uint8).tobytes()
    dt = np.dtype(kind)
    v = np.frombuffer(raw, dtype=dt).astype(np.float64) * factor
    if dt.kind == "i":
        info = np.iinfo(dt)
        v = np.clip(np.rint(v), info.min, info.max)
    return v.astype(dt).tobytes()


def pcm_scale(path, factor, block=4 * 1024 * 1024):
    """Skaliert die PCM-Samples einer WAV- oder AIFF-Datei an Ort und Stelle."""
    with open(path, "r+b") as f:
        head = f.read(12)
        f.seek(0)
        if head[:4] == b"RIFF":
            start, size, kind, align = _wav_layout(f)
        elif head[:4] == b"FORM":
            start, size, kind, align = _aiff_layout(f)
        else:
            raise LoudnessError("Weder WAV noch AIFF.")
        file_size = os.fstat(f.fileno()).st_size
        size = min(size, file_size - start)
        block -= block % max(1, align)
        width = 3 if kind.endswith("3") else (1 if kind in ("u8", "i1") else int(kind[-1]))
        size -= size % width
        done = 0
        while done < size:
            n = min(block, size - done)
            f.seek(start + done)
            raw = f.read(n)
            n = len(raw) - len(raw) % width
            if n <= 0:
                break
            f.seek(start + done)
            f.write(_scale_block(raw[:n], kind, factor))
            done += n
        f.flush()
        os.fsync(f.fileno())


# --------------------------------------------------------------------------
# Opus: Output Gain im Kopf (verlustfrei)
# --------------------------------------------------------------------------
def _ogg_crc(data):
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else (crc << 1)
            crc &= 0xFFFFFFFF
    return crc


def opus_add_gain(path, gain_db):
    with open(path, "r+b") as f:
        head = bytearray(f.read(65536))
        if head[:4] != b"OggS":
            raise LoudnessError("Keine Ogg-Datei.")
        nseg = head[26]
        seg_table = head[27:27 + nseg]
        body = 27 + nseg
        page_len = body + sum(seg_table)
        if head[body:body + 8] != b"OpusHead":
            raise LoudnessError("Opus-Kopf nicht gefunden.")
        old = struct.unpack("<h", head[body + 16:body + 18])[0]
        new = max(-32768, min(32767, old + int(round(gain_db * 256))))
        head[body + 16:body + 18] = struct.pack("<h", new)
        page = bytearray(head[:page_len])
        page[22:26] = b"\x00\x00\x00\x00"
        page[22:26] = struct.pack("<I", _ogg_crc(page))
        f.seek(0)
        f.write(page)
    return (new - old) / 256.0


# --------------------------------------------------------------------------
# Neukodierung (FLAC / ALAC verlustfrei, sonst verlustbehaftet)
# --------------------------------------------------------------------------
def _probe_bits(path):
    try:
        import mutagen
        f = mutagen.File(path)
        return getattr(f.info, "bits_per_sample", 0) or getattr(f.info, "bits_per_raw_sample", 0) or 16
    except Exception:
        return 16


def _ffmpeg_reencode(ffmpeg, path, fmt, gain_db, bitrate=0):
    fmt = fmt.upper()
    ext = os.path.splitext(path)[1]
    fd, tmp = tempfile.mkstemp(suffix=ext, prefix=".mog-gain-", dir=os.path.dirname(path) or None)
    os.close(fd)
    vol = f"volume={gain_db:.4f}dB:precision=double,asetpts=N/SR/TB"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", path,
           "-map", "0:a:0", "-map_metadata", "0", "-af", vol]
    if fmt == "FLAC":
        bits = _probe_bits(path)
        cmd += ["-c:a", "flac", "-compression_level", "8"]
        cmd += ["-sample_fmt", "s16"] if bits <= 16 else ["-sample_fmt", "s32", "-bits_per_raw_sample", str(bits)]
    elif fmt == "ALAC":
        bits = _probe_bits(path)
        cmd += ["-c:a", "alac", "-sample_fmt", "s16p" if bits <= 16 else "s32p"]
        if bits > 16:
            cmd += ["-bits_per_raw_sample", str(bits)]
        cmd += ["-f", "ipod"]
    else:
        enc = _REENCODE.get(fmt)
        if not enc:
            raise LoudnessError(f"Für {fmt} ist keine Neukodierung vorgesehen.")
        kbps = max(64, round((bitrate or 0) / 1000) or 256)
        cmd += ["-c:a", enc, "-b:a", f"{kbps}k"]
        if fmt == "AAC":
            cmd += ["-f", "ipod"]
        elif fmt == "WMA":
            cmd += ["-f", "asf"]
        elif fmt == "OGG":
            cmd += ["-f", "ogg"]
    cmd.append(tmp)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=1800, **no_window_flags())
        if p.returncode != 0 or os.path.getsize(tmp) == 0:
            raise LoudnessError(p.stderr.decode("utf-8", "replace").strip()[-300:] or "ffmpeg-Fehler")
        copy_all_tags(path, tmp)
        _overwrite_contents(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def copy_all_tags(src, dst):
    """Überträgt sämtliche Tags samt Cover von src nach dst (gleicher Containertyp)."""
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    s, d = mutagen.File(src), mutagen.File(dst)
    if s is None or d is None or s.tags is None:
        return
    if isinstance(s, FLAC) and isinstance(d, FLAC):
        if d.tags is None:
            d.add_tags()
        d.tags.clear()
        for k, v in s.tags.items():
            d.tags[k] = v
        d.clear_pictures()
        for pic in s.pictures:
            d.add_picture(pic)
        d.save()
    elif isinstance(s, MP4) and isinstance(d, MP4):
        if d.tags is None:
            d.add_tags()
        d.tags.clear()
        for k, v in s.tags.items():
            d.tags[k] = v
        d.save()
    else:
        if d.tags is None:
            try:
                d.add_tags()
            except Exception:
                return
        try:
            d.tags.clear()
            for k, v in s.tags.items():
                d.tags[k] = v
            d.save()
        except Exception:
            pass        # ffmpeg hat die Metadaten bereits übernommen (-map_metadata 0)


# ==========================================================================
# ReplayGain-Tags (Datei bleibt unverändert)
# ==========================================================================
def write_replaygain(path, lufs, peak_db):
    """Schreibt REPLAYGAIN_TRACK_GAIN/-PEAK (Bezug −18 LUFS); bei Opus R128_TRACK_GAIN."""
    from mutagen.apev2 import APEv2
    from mutagen.asf import ASF
    from mutagen.id3 import ID3, TXXX
    from mutagen.mp4 import MP4, MP4FreeForm
    from . import tags as tagmod
    f = tagmod._load(path)
    kind = tagmod._kind(f)
    gain = REPLAYGAIN_REF - lufs
    g_txt = f"{gain:+.2f} dB"
    p_txt = f"{10 ** (peak_db / 20.0):.6f}"
    if f.tags is None:
        f.add_tags()
    t = f.tags
    if type(f).__name__ == "OggOpus":
        t["R128_TRACK_GAIN"] = [str(int(round((R128_REF - lufs) * 256)))]
        for k in ("REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_TRACK_PEAK"):
            if k in t:
                del t[k]
        f.save()
        return
    if kind == "id3" and isinstance(t, ID3):
        for k, v in (("REPLAYGAIN_TRACK_GAIN", g_txt), ("REPLAYGAIN_TRACK_PEAK", p_txt)):
            t.delall(f"TXXX:{k}")
            t.delall(f"TXXX:{k.lower()}")
            t.add(TXXX(encoding=1, desc=k, text=[v]))
        try:
            f.save(v2_version=3)
        except TypeError:
            f.save()
        return
    if kind == "mp4" and isinstance(f, MP4):
        t["----:com.apple.iTunes:replaygain_track_gain"] = [MP4FreeForm(g_txt.encode())]
        t["----:com.apple.iTunes:replaygain_track_peak"] = [MP4FreeForm(p_txt.encode())]
        f.save()
        return
    if kind == "vorbis":
        t["REPLAYGAIN_TRACK_GAIN"] = [g_txt]
        t["REPLAYGAIN_TRACK_PEAK"] = [p_txt]
        f.save()
        return
    if kind == "asf" and isinstance(f, ASF):
        t["replaygain_track_gain"] = [g_txt]
        t["replaygain_track_peak"] = [p_txt]
        f.save()
        return
    if kind == "ape" and isinstance(t, APEv2):
        t["REPLAYGAIN_TRACK_GAIN"] = g_txt
        t["REPLAYGAIN_TRACK_PEAK"] = p_txt
        f.save()
        return
    raise LoudnessError("Für dieses Format kann MOG keine ReplayGain-Tags schreiben.")


def format_lufs(v):
    return "" if v is None else f"{v:.1f}".replace(".", ",")
