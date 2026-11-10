"""Einfache BPM-Erkennung (Onset-Hüllkurve + Autokorrelation), nur numpy.

Spotify liefert für neue Apps seit Ende 2024 keine BPM mehr – daher analysiert
MOG das Tempo lokal. Bereich wie bei rekordbox wählbar (z. B. 78–155).
"""
import numpy as np

SR = 11025
HOP = 128
WIN = 1024

BPM_RANGES = {
    "58–115": (58, 115), "68–135": (68, 135), "78–155": (78, 155),
    "88–175": (88, 175), "98–195": (98, 195),
}
DEFAULT_RANGE = "78–155"


def onset_envelope(y, sr=SR):
    if len(y) < WIN * 4:
        return np.zeros(0)
    n = 1 + (len(y) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(WIN)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    # Frequenzbänder bis ~5 kHz, logarithmisch komprimiert
    mag = np.log1p(100.0 * mag[:, : int(5000 / (sr / WIN))])
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    # lokalen Mittelwert abziehen (≈ 0,5 s)
    k = max(1, int(0.5 * sr / HOP))
    smooth = np.convolve(flux, np.ones(k) / k, mode="same")
    env = np.maximum(0.0, flux - smooth)
    # leicht glätten, damit Autokorrelations-Spitzen nicht zwischen Frames fallen
    g = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    env = np.convolve(env, g / g.sum(), mode="same")
    if env.std() > 0:
        env = (env - env.mean()) / env.std()
    return env


def estimate_bpm(y, sr=SR, bpm_min=78, bpm_max=155):
    """Schätzt das Tempo. Gibt (bpm, konfidenz 0..1) zurück oder (None, 0)."""
    env = onset_envelope(y, sr)
    if len(env) < 200:
        return None, 0.0
    fps = sr / HOP
    n = len(env)
    f = np.fft.rfft(env, 2 * n)
    acf = np.fft.irfft(f * np.conj(f))[:n]
    acf /= acf[0] if acf[0] else 1.0

    lag_min = int(fps * 60 / 220)
    lag_max = min(n // 4, int(fps * 60 / 50))
    lags = np.arange(lag_min, lag_max, 0.25)
    if len(lags) < 3:
        return None, 0.0

    def acf_at(l):
        l = np.asarray(l, dtype=float)
        i = np.floor(l).astype(int)
        frac = l - i
        i = np.clip(i, 0, n - 2)
        return acf[i] * (1 - frac) + acf[i + 1] * frac

    # Kammfilter: Grundschlag + Vielfache stärken die richtige Periode
    score = np.zeros(len(lags))
    for k, w in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.25)):
        score += w * acf_at(lags * k)
    best = int(np.argmax(score))
    # parabolische Interpolation für Nachkommastellen
    if 0 < best < len(score) - 1:
        a, b, c = score[best - 1], score[best], score[best + 1]
        denom = a - 2 * b + c
        offset = 0.5 * (a - c) / denom if denom else 0.0
    else:
        offset = 0.0
    lag = lags[best] + offset * 0.25
    bpm = 60.0 * fps / lag
    while bpm < bpm_min:
        bpm *= 2
    while bpm >= bpm_max + 0.5:
        bpm /= 2
    conf = float(np.clip((score[best] - np.median(score)) / (np.max(score) + 1e-9), 0, 1))
    return float(bpm), conf


def analyze_file(ffmpeg, path, duration=0.0, bpm_min=78, bpm_max=155, round_int=True):
    from .encoder import decode_mono
    # Ausschnitt aus der Mitte (Intros/Outros verfälschen oft)
    length = 90.0
    start = 0.0
    if duration and duration > length + 30:
        start = max(0.0, duration * 0.35 - length / 2)
    y = decode_mono(ffmpeg, path, SR, start, length)
    bpm, conf = estimate_bpm(y, SR, bpm_min, bpm_max)
    if bpm is None:
        return None, 0.0
    return (float(round(bpm)) if round_int else round(bpm, 1)), conf
