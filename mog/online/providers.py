"""Tag-Suche in Online-Datenbanken: MusicBrainz, Discogs, Spotify, AcoustID.

Hinweise:
- MusicBrainz: frei, max. 1 Anfrage/Sekunde, benötigt aussagekräftigen User-Agent.
- Discogs: persönlicher Token (kostenlos) – ideal für Label, Genre und Stil.
- Spotify: eigene App unter developer.spotify.com nötig (Client-ID/Secret). Seit Feb. 2026
  muss der App-Inhaber Spotify Premium haben; BPM/Audio-Features gibt es für neue Apps
  seit Nov. 2024 nicht mehr, Album-Labels wurden ebenfalls entfernt.
- AcoustID: Erkennung per Audio-Fingerabdruck (fpcalc + kostenloser API-Key).
"""
import base64
import threading
import time
from dataclasses import dataclass, field

import requests

from mog import __version__

TIMEOUT = 15


@dataclass
class TagResult:
    source: str
    artist: str = ""
    title: str = ""
    album: str = ""
    albumartist: str = ""
    year: str = ""
    track: str = ""
    genre: str = ""
    label: str = ""
    bpm: str = ""
    key: str = ""
    isrc: str = ""
    duration: float = 0.0
    cover_url: str = ""
    score: int = 0
    info: str = ""
    extra: dict = field(default_factory=dict)

    def fields(self):
        return {k: getattr(self, k) for k in ("artist", "title", "album", "albumartist",
                                               "year", "track", "genre", "label", "bpm", "key")}


class ProviderError(Exception):
    pass


def user_agent(contact=""):
    contact = contact.strip() or "https://github.com/"
    return f"MusicOrganizer-MOG/{__version__} ( {contact} )"


def _session(contact=""):
    s = requests.Session()
    s.headers["User-Agent"] = user_agent(contact)
    s.headers["Accept"] = "application/json"
    return s


def _check(r, name):
    if r.status_code == 401:
        raise ProviderError(f"{name}: Zugangsdaten ungültig (401). Bitte in den Einstellungen prüfen.")
    if r.status_code == 403:
        raise ProviderError(f"{name}: Zugriff verweigert (403).")
    if r.status_code == 429:
        raise ProviderError(f"{name}: Zu viele Anfragen – bitte kurz warten.")
    if r.status_code >= 400:
        raise ProviderError(f"{name}: HTTP-Fehler {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise ProviderError(f"{name}: unerwartete Antwort") from e


# --------------------------------------------------------------------------
# MusicBrainz
# --------------------------------------------------------------------------
_mb_lock = threading.Lock()
_mb_last = [0.0]


def _mb_wait():
    with _mb_lock:
        d = time.time() - _mb_last[0]
        if d < 1.1:
            time.sleep(1.1 - d)
        _mb_last[0] = time.time()


def _lucene(s):
    for ch in '\\+-&|!(){}[]^"~*?:/':
        s = s.replace(ch, f"\\{ch}")
    return s


def musicbrainz_search(artist, title, contact="", limit=15):
    if not title and not artist:
        return []
    q = []
    if title:
        q.append(f'recording:"{_lucene(title)}"')
    if artist:
        q.append(f'artist:"{_lucene(artist)}"')
    _mb_wait()
    s = _session(contact)
    try:
        r = s.get("https://musicbrainz.org/ws/2/recording",
                  params={"query": " AND ".join(q), "fmt": "json", "limit": limit}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError(f"MusicBrainz nicht erreichbar: {e}") from e
    data = _check(r, "MusicBrainz")
    out = []
    for rec in data.get("recordings", []):
        credit = "".join(c.get("name", "") + c.get("joinphrase", "") for c in rec.get("artist-credit", []))
        releases = rec.get("releases", []) or []

        def rel_rank(rel):
            rg = rel.get("release-group", {})
            return (rel.get("status") != "Official", rg.get("primary-type") != "Single" and
                    rg.get("primary-type") != "Album", rel.get("date", "9999") or "9999")
        rel = sorted(releases, key=rel_rank)[0] if releases else {}
        tags = sorted(rec.get("tags", []) or [], key=lambda t: -t.get("count", 0))
        track_no = ""
        try:
            m = rel.get("media", [{}])[0]
            tr = m.get("track", [{}])[0]
            track_no = str(tr.get("number", "")) if tr else ""
        except (IndexError, AttributeError):
            pass
        rel_artist = "".join(c.get("name", "") + c.get("joinphrase", "")
                             for c in rel.get("artist-credit", []) or [])
        res = TagResult(
            source="MusicBrainz",
            artist=credit,
            title=rec.get("title", ""),
            album=rel.get("title", ""),
            albumartist=rel_artist if rel_artist and rel_artist != credit else "",
            year=(rel.get("date") or rec.get("first-release-date") or "")[:4],
            track=track_no,
            genre=tags[0]["name"].title() if tags else "",
            isrc=(rec.get("isrcs") or [""])[0],
            duration=(rec.get("length") or 0) / 1000.0,
            cover_url=f"https://coverartarchive.org/release/{rel['id']}/front-250" if rel.get("id") else "",
            score=int(rec.get("score", 0)),
            info=(rel.get("release-group", {}) or {}).get("primary-type", "") or "",
            extra={"release_id": rel.get("id", ""), "recording_id": rec.get("id", "")},
        )
        out.append(res)
    return out


def musicbrainz_release_label(release_id, contact=""):
    """Label einer Veröffentlichung nachladen (eigene Anfrage)."""
    if not release_id:
        return ""
    _mb_wait()
    try:
        r = _session(contact).get(f"https://musicbrainz.org/ws/2/release/{release_id}",
                                  params={"inc": "labels", "fmt": "json"}, timeout=TIMEOUT)
        data = _check(r, "MusicBrainz")
    except (requests.RequestException, ProviderError):
        return ""
    for li in data.get("label-info", []) or []:
        lab = (li.get("label") or {}).get("name")
        if lab:
            return lab
    return ""


# --------------------------------------------------------------------------
# Discogs
# --------------------------------------------------------------------------
def discogs_search(artist, title, token, contact="", limit=15):
    if not token:
        raise ProviderError("Discogs: Bitte zuerst einen persönlichen Token in den Einstellungen eintragen.")
    s = _session(contact)
    s.headers["Authorization"] = f"Discogs token={token}"
    params = {"type": "release", "per_page": limit}
    if artist:
        params["artist"] = artist
    if title:
        params["track"] = title
    try:
        r = s.get("https://api.discogs.com/database/search", params=params, timeout=TIMEOUT)
        data = _check(r, "Discogs")
        if not data.get("results") and artist and title:
            r = s.get("https://api.discogs.com/database/search",
                      params={"type": "release", "per_page": limit, "q": f"{artist} {title}"},
                      timeout=TIMEOUT)
            data = _check(r, "Discogs")
    except requests.RequestException as e:
        raise ProviderError(f"Discogs nicht erreichbar: {e}") from e
    out = []
    for it in data.get("results", []):
        full = it.get("title", "")
        rel_artist, _, rel_title = full.partition(" - ")
        styles = it.get("style") or []
        genres = it.get("genre") or []
        labels = [l for l in (it.get("label") or []) if l]
        out.append(TagResult(
            source="Discogs",
            artist=artist or _strip_discogs_num(rel_artist),
            title=title,
            album=rel_title or full,
            albumartist=_strip_discogs_num(rel_artist),
            year=str(it.get("year", "") or ""),
            genre=styles[0] if styles else (genres[0] if genres else ""),
            label=_strip_discogs_num(labels[0]) if labels else "",
            cover_url=it.get("cover_image", "") or it.get("thumb", ""),
            info=", ".join((it.get("format") or [])[:3]) + (f" · {it.get('catno')}" if it.get("catno") else ""),
            extra={"genres": genres, "styles": styles, "discogs_id": it.get("id")},
        ))
    return out


def _strip_discogs_num(s):
    """'Artist (2)' -> 'Artist'."""
    import re
    return re.sub(r"\s+\(\d+\)$", "", (s or "").strip())


# --------------------------------------------------------------------------
# Spotify
# --------------------------------------------------------------------------
_sp_token = {"value": None, "expires": 0.0, "id": None}


def _spotify_token(client_id, client_secret):
    if not client_id or not client_secret:
        raise ProviderError("Spotify: Bitte Client-ID und Client-Secret in den Einstellungen eintragen.")
    if _sp_token["value"] and _sp_token["id"] == client_id and time.time() < _sp_token["expires"] - 60:
        return _sp_token["value"]
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        r = requests.post("https://accounts.spotify.com/api/token",
                          data={"grant_type": "client_credentials"},
                          headers={"Authorization": f"Basic {auth}"}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError(f"Spotify nicht erreichbar: {e}") from e
    data = _check(r, "Spotify")
    _sp_token.update(value=data["access_token"], expires=time.time() + data.get("expires_in", 3600),
                     id=client_id)
    return _sp_token["value"]


def spotify_search(artist, title, client_id, client_secret, limit=10):
    tok = _spotify_token(client_id, client_secret)
    q = " ".join(x for x in (f"track:{title}" if title else "", f"artist:{artist}" if artist else "") if x)
    try:
        r = requests.get("https://api.spotify.com/v1/search",
                         params={"q": q, "type": "track", "limit": min(limit, 10)},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError(f"Spotify nicht erreichbar: {e}") from e
    data = _check(r, "Spotify")
    out = []
    for it in (data.get("tracks") or {}).get("items", []):
        alb = it.get("album") or {}
        imgs = sorted(alb.get("images") or [], key=lambda i: abs((i.get("width") or 0) - 300))
        out.append(TagResult(
            source="Spotify",
            artist=", ".join(a.get("name", "") for a in it.get("artists", [])),
            title=it.get("name", ""),
            album=alb.get("name", ""),
            albumartist=", ".join(a.get("name", "") for a in alb.get("artists", [])),
            year=(alb.get("release_date") or "")[:4],
            track=str(it.get("track_number", "") or ""),
            isrc=(it.get("external_ids") or {}).get("isrc", ""),
            duration=(it.get("duration_ms") or 0) / 1000.0,
            cover_url=imgs[0]["url"] if imgs else "",
            info=(alb.get("album_type") or "").title(),
            extra={"spotify_id": it.get("id")},
        ))
    return out


# --------------------------------------------------------------------------
# AcoustID (Audio-Fingerabdruck)
# --------------------------------------------------------------------------
def acoustid_lookup(fingerprint, duration, api_key, contact=""):
    if not api_key:
        raise ProviderError("AcoustID: Bitte einen API-Key in den Einstellungen eintragen "
                            "(kostenlos auf acoustid.org).")
    try:
        r = _session(contact).post(
            "https://api.acoustid.org/v2/lookup",
            data={"client": api_key, "meta": "recordings releasegroups compress",
                  "duration": int(duration), "fingerprint": fingerprint, "format": "json"},
            timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError(f"AcoustID nicht erreichbar: {e}") from e
    data = _check(r, "AcoustID")
    if data.get("status") != "ok":
        raise ProviderError(f"AcoustID: {(data.get('error') or {}).get('message', 'Fehler')}")
    out = []
    for res in data.get("results", []):
        score = int(round(res.get("score", 0) * 100))
        for rec in res.get("recordings", []) or []:
            rgs = rec.get("releasegroups") or []
            rg = rgs[0] if rgs else {}
            out.append(TagResult(
                source="AcoustID",
                artist="".join(a.get("name", "") + a.get("joinphrase", "") for a in rec.get("artists", []) or []),
                title=rec.get("title", ""),
                album=rg.get("title", ""),
                duration=float(rec.get("duration") or 0),
                score=score,
                info=rg.get("type", "") or "",
                extra={"recording_id": rec.get("id")},
            ))
    out.sort(key=lambda r: -r.score)
    return out


def download_image(url, contact=""):
    if not url:
        return None
    try:
        r = _session(contact).get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return r.content, ctype
    except requests.RequestException:
        pass
    return None
