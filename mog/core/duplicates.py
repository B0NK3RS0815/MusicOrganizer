"""Duplikaterkennung: Tags + Länge, identischer Dateiinhalt, akustischer Fingerabdruck."""
import hashlib
import re
import threading
import unicodedata
from collections import defaultdict

from .formats import get_format

_FEAT = re.compile(r"\s*[\(\[]?\s*\b(feat\.?|ft\.?|featuring)\s+[^\)\]]*[\)\]]?", re.I)
_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_MIX_WORDS = re.compile(r"\b(original|extended|radio|club|album|single)\s+(mix|edit|version)\b", re.I)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def normalize(text, ignore_mix=False):
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("&", " and ").replace("+", " and ")
    t = _FEAT.sub(" ", t)
    if ignore_mix:
        t = _BRACKETS.sub(" ", t)
    else:
        # "(Original Mix)" ist gleichbedeutend mit keiner Angabe
        t = re.sub(r"[\(\[]\s*original\s+mix\s*[\)\]]", " ", t)
    t = _NON_ALNUM.sub(" ", t)
    t = re.sub(r"\bthe\b", " ", t)
    return " ".join(t.split())


def quality_score(t):
    """Höher = besser. Dient zur automatischen Auswahl der zu behaltenden Datei."""
    s = 0.0
    if get_format(t.fmt).lossless:
        s += 10_000 + (t.bits or 16) * 10 + (t.samplerate or 44100) / 1000
    else:
        s += min(t.bitrate or 0, 500_000) / 1000
        if t.fmt == "MP3":
            s += 5  # bei gleicher Bitrate MP3 leicht bevorzugen (DJ-Kompatibilität)
    if not t.tags_missing:
        s += 3
    if t.has_cover:
        s += 1
    if t.bpm:
        s += 1
    if t.missing:
        s -= 100_000
    return s


class DuplicateGroup:
    def __init__(self, reason, tracks, similarity=None):
        self.reason = reason          # "tags" | "identisch" | "fingerprint"
        self.tracks = sorted(tracks, key=quality_score, reverse=True)
        self.similarity = similarity

    @property
    def best(self):
        return self.tracks[0]


def _cluster_by_duration(tracks, tol):
    tracks = sorted(tracks, key=lambda t: t.duration or 0)
    clusters, cur = [], []
    for t in tracks:
        if cur and (t.duration or 0) - (cur[-1].duration or 0) > tol:
            clusters.append(cur)
            cur = []
        cur.append(t)
    if cur:
        clusters.append(cur)
    return clusters


def find_by_tags(tracks, duration_tol=2.0, ignore_mix=False, ignore_duration=False):
    buckets = defaultdict(list)
    for t in tracks:
        a, ti = normalize(t.artist, ignore_mix), normalize(t.title, ignore_mix)
        if not ti:
            continue
        buckets[(a, ti)].append(t)
    groups = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        clusters = [items] if ignore_duration else _cluster_by_duration(items, duration_tol)
        for c in clusters:
            if len(c) >= 2:
                groups.append(DuplicateGroup("tags", c))
    return groups


def file_hash(path, chunk=1 << 20):
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_identical(tracks, get_hash, progress=None, cancel=None):
    """Byte-identische Dateien. get_hash(track) liefert (ggf. gecachten) Hash."""
    by_size = defaultdict(list)
    for t in tracks:
        if t.size and not t.missing:
            by_size[t.size].append(t)
    cands = [ts for ts in by_size.values() if len(ts) > 1]
    total = sum(len(c) for c in cands)
    done = 0
    groups = []
    for ts in cands:
        by_hash = defaultdict(list)
        for t in ts:
            if cancel is not None and cancel.is_set():
                return groups
            try:
                h = get_hash(t)
            except OSError:
                h = None
            done += 1
            if progress:
                progress(done, total)
            if h:
                by_hash[h].append(t)
        for items in by_hash.values():
            if len(items) > 1:
                groups.append(DuplicateGroup("identisch", items, 1.0))
    return groups


class _UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def find_by_fingerprint(tracks, get_fp, threshold=0.85, progress=None, cancel=None,
                        min_shared_keys=6):
    """Akustische Duplikate. get_fp(track) -> np.uint32-Array oder None."""
    from .fingerprint import similarity
    fps = {}
    total = len(tracks)
    for i, t in enumerate(tracks, 1):
        if cancel is not None and cancel.is_set():
            return []
        if t.missing:
            continue
        try:
            fp = get_fp(t)
        except Exception:
            fp = None
        if fp is not None and len(fp) >= 30:
            fps[t.id] = fp
        if progress:
            progress(i, total, "Fingerabdrücke berechnen")

    # Index: obere 16 Bit der ersten ~120 Werte (≈ 15 s ab Sekunde 2)
    index = defaultdict(list)
    for tid, fp in fps.items():
        keys = set(int(v) >> 16 for v in fp[16:136])
        for k in keys:
            index[k].append(tid)
    cap = max(50, len(fps) // 50)
    pair_counts = defaultdict(int)
    for k, ids in index.items():
        if len(ids) < 2 or len(ids) > cap:
            continue
        for i in range(len(ids)):
            a = ids[i]
            for b in ids[i + 1:]:
                pair_counts[(a, b) if a < b else (b, a)] += 1

    cands = [p for p, c in pair_counts.items() if c >= min_shared_keys]
    uf = _UnionFind()
    sims = {}
    by_id = {t.id: t for t in tracks}
    for n, (a, b) in enumerate(cands, 1):
        if cancel is not None and cancel.is_set():
            break
        s = similarity(fps[a], fps[b])
        if s >= threshold:
            uf.union(a, b)
            sims[(a, b)] = s
        if progress and n % 50 == 0:
            progress(n, len(cands), "Fingerabdrücke vergleichen")
    clusters = defaultdict(list)
    for (a, b) in sims:
        for x in (a, b):
            r = uf.find(x)
            if by_id[x] not in clusters[r]:
                clusters[r].append(by_id[x])
    groups = []
    for r, items in clusters.items():
        if len(items) >= 2:
            ss = [s for (a, b), s in sims.items() if uf.find(a) == r]
            groups.append(DuplicateGroup("fingerprint", items, min(ss) if ss else None))
    return groups


def merge_groups(*group_lists):
    """Führt Gruppen zusammen, die gemeinsame Titel enthalten."""
    uf = _UnionFind()
    reasons = defaultdict(set)
    sims = {}
    tracks = {}
    for gl in group_lists:
        for g in gl:
            ids = [t.id for t in g.tracks]
            for t in g.tracks:
                tracks[t.id] = t
            for x in ids[1:]:
                uf.union(ids[0], x)
            reasons[ids[0]].add(g.reason)
            if g.similarity is not None:
                sims[ids[0]] = g.similarity
    clusters = defaultdict(list)
    for tid in tracks:
        clusters[uf.find(tid)].append(tracks[tid])
    rmap = defaultdict(set)
    smap = {}
    for first, rs in reasons.items():
        rmap[uf.find(first)] |= rs
        if first in sims:
            smap[uf.find(first)] = min(smap.get(uf.find(first), 1.0), sims[first])
    out = []
    for r, items in clusters.items():
        if len(items) >= 2:
            order = ["identisch", "fingerprint", "tags"]
            reason = " + ".join(x for x in order if x in rmap[r])
            out.append(DuplicateGroup(reason, items, smap.get(r)))
    out.sort(key=lambda g: (g.best.artist.lower(), g.best.title.lower()))
    return out


def run_search(tracks, use_tags=True, use_identical=True, use_fingerprint=False, lib=None,
               fpcalc=None, duration_tol=2.0, ignore_mix=False, threshold=0.85,
               progress=None, cancel=None):
    """Kombinierbare Suchmethoden; Ergebnisse werden zu Gruppen zusammengeführt."""
    cancel = cancel or threading.Event()
    results = []

    def get_hash(t):
        h = lib.get_hash(t.id) if lib else None
        if not h:
            h = file_hash(t.path)
            if lib:
                lib.set_hash(t.id, h)
        return h

    def get_fp(t):
        from .fingerprint import compute_raw, from_blob, to_blob
        if lib:
            blob, _d = lib.get_fingerprint(t.id)
            if blob:
                return from_blob(blob)
        d, fp = compute_raw(fpcalc, t.path)
        if lib:
            lib.set_fingerprint(t.id, to_blob(fp), d)
        return fp

    if use_tags:
        if progress:
            progress(0, 0, "Vergleiche Tags …")
        results.append(find_by_tags(tracks, duration_tol, ignore_mix))
    if use_identical and not cancel.is_set():
        results.append(find_identical(
            tracks, get_hash,
            (lambda d, t: progress(d, t, "Prüfe identische Dateien")) if progress else None, cancel))
    if use_fingerprint and fpcalc and not cancel.is_set():
        results.append(find_by_fingerprint(tracks, get_fp, threshold, progress, cancel))
    return merge_groups(*results)
