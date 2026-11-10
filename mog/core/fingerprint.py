"""Akustische Fingerabdrücke über Chromaprint (fpcalc)."""
import json
import subprocess

import numpy as np

from .fileops import no_window_flags
from .paths import find_tool


class FingerprintError(Exception):
    pass


def find_fpcalc(configured=None):
    return find_tool("fpcalc", configured)


def compute_raw(fpcalc, path, length=120):
    """Gibt (dauer, np.uint32-Array) zurück."""
    p = subprocess.run([fpcalc, "-raw", "-json", "-length", str(length), path],
                       capture_output=True, text=True, timeout=180, **no_window_flags())
    if p.returncode != 0 or not p.stdout.strip():
        raise FingerprintError(p.stderr.strip()[-300:] or "fpcalc-Fehler")
    data = json.loads(p.stdout)
    fp = np.array(data.get("fingerprint", []), dtype=np.int64).astype(np.uint32)
    return float(data.get("duration", 0)), fp


def compute_compressed(fpcalc, path, length=120):
    """Für die AcoustID-Abfrage: (dauer, fingerprint-string)."""
    p = subprocess.run([fpcalc, "-json", "-length", str(length), path],
                       capture_output=True, text=True, timeout=180, **no_window_flags())
    if p.returncode != 0 or not p.stdout.strip():
        raise FingerprintError(p.stderr.strip()[-300:] or "fpcalc-Fehler")
    data = json.loads(p.stdout)
    return float(data.get("duration", 0)), data.get("fingerprint", "")


def to_blob(fp):
    return np.asarray(fp, dtype=np.uint32).tobytes()


def from_blob(blob):
    return np.frombuffer(blob, dtype=np.uint32)


def _popcount(x):
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(x)
    x = x.astype(np.uint32)
    return np.unpackbits(x.view(np.uint8)).reshape(len(x), 32).sum(axis=1)


def similarity(a, b, max_offset=10):
    """1 - Bitfehlerrate bei bester Verschiebung (1.0 = identisch, ~0.5 = unähnlich)."""
    if len(a) < 20 or len(b) < 20:
        return 0.0
    best = 0.0
    for off in range(-max_offset, max_offset + 1):
        if off >= 0:
            x, y = a[off:], b
        else:
            x, y = a, b[-off:]
        m = min(len(x), len(y))
        if m < 20:
            continue
        diff = _popcount(np.bitwise_xor(x[:m], y[:m])).sum()
        sim = 1.0 - diff / (32.0 * m)
        if sim > best:
            best = sim
    return best
