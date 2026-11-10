"""Lesen und Schreiben von Tags für alle gängigen Audioformate (über mutagen).

Einheitliche Felder: siehe track.TAG_FIELDS. Cover werden als (bytes, mime) behandelt.
"""
import base64
import os
import re
import struct

import mutagen
from mutagen.apev2 import APEv2, APEValue, BINARY
from mutagen.asf import ASF, ASFByteArrayAttribute
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (APIC, COMM, ID3, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1,
                         TPE2, TPUB, TRCK)
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from .formats import format_for_extension, get_format
from .track import TAG_FIELDS, Track, parse_bpm


class TagError(Exception):
    pass


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
def _join(values):
    out = []
    for v in values or []:
        s = str(v).strip()
        if s:
            out.append(s)
    return "; ".join(out)


def _first(values):
    for v in values or []:
        s = str(v).strip()
        if s:
            return s
    return ""


def guess_mime(data):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


_FILENAME_RE = re.compile(r"^\s*(?:\d{1,3}\s*[-._)]\s*)?(?P<artist>.+?)\s+[-–—]\s+(?P<title>.+?)\s*$")


def parse_filename(path):
    """'01 - Artist - Title.mp3' -> ('Artist', 'Title')."""
    stem = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
    m = _FILENAME_RE.match(stem)
    if m:
        return m.group("artist").strip(), m.group("title").strip()
    return "", stem.strip()


def _kind(f):
    """Ermittelt das Tag-System einer geladenen mutagen-Datei."""
    if isinstance(f, MP4):
        return "mp4"
    if isinstance(f, ASF):
        return "asf"
    tags = f.tags
    if isinstance(tags, ID3):
        return "id3"
    if isinstance(tags, APEv2):
        return "ape"
    if tags is not None and hasattr(tags, "keys") and type(tags).__name__.startswith("VC"):
        return "vorbis"
    # noch keine Tags vorhanden -> nach Dateityp entscheiden
    name = type(f).__name__
    if name in ("MP3", "EasyMP3", "WAVE", "AIFF", "DSF", "TrueAudio", "DSDIFF"):
        return "id3"
    if name in ("FLAC", "OggVorbis", "OggOpus", "OggFLAC", "OggSpeex"):
        return "vorbis"
    if name in ("MonkeysAudio", "WavPack", "Musepack", "OptimFROG"):
        return "ape"
    return None


# --------------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------------
def _read_id3(tags):
    d = {}
    if tags is None:
        return d, None
    g = lambda fid: _join(tags[fid].text) if fid in tags else ""
    d["artist"] = g("TPE1")
    d["title"] = g("TIT2")
    d["album"] = g("TALB")
    d["albumartist"] = g("TPE2")
    d["genre"] = g("TCON")
    d["year"] = g("TDRC") or g("TYER")
    d["track"] = g("TRCK")
    d["bpm"] = g("TBPM")
    d["key"] = g("TKEY")
    d["label"] = g("TPUB")
    comm = ""
    for c in tags.getall("COMM"):
        if c.desc in ("", "Comment") and _join(c.text):
            comm = _join(c.text)
            break
    if not comm:
        for c in tags.getall("COMM"):
            if _join(c.text) and not c.desc.startswith("iTun"):
                comm = _join(c.text)
                break
    d["comment"] = comm
    cover = None
    apics = tags.getall("APIC")
    if apics:
        front = [a for a in apics if a.type == 3] or apics
        cover = (front[0].data, front[0].mime or guess_mime(front[0].data))
    return d, cover


def _mp4_free(tags, name):
    key = f"----:com.apple.iTunes:{name}"
    for k in tags.keys():
        if k.lower() == key.lower():
            vals = tags[k]
            return _first(v.decode("utf-8", "replace") if isinstance(v, bytes) else v for v in vals)
    return ""


def _read_mp4(tags):
    d = {}
    if tags is None:
        return d, None
    g = lambda k: _join(tags.get(k, []))
    d["artist"] = g("\xa9ART")
    d["title"] = g("\xa9nam")
    d["album"] = g("\xa9alb")
    d["albumartist"] = g("aART")
    d["genre"] = g("\xa9gen")
    d["year"] = g("\xa9day")
    trkn = tags.get("trkn")
    d["track"] = ""
    if trkn:
        n, tot = trkn[0]
        d["track"] = f"{n}/{tot}" if tot else (str(n) if n else "")
    bpm = _mp4_free(tags, "BPM")
    if not bpm and tags.get("tmpo"):
        bpm = str(tags["tmpo"][0])
    d["bpm"] = bpm
    d["key"] = _mp4_free(tags, "initialkey") or _mp4_free(tags, "KEY")
    d["label"] = _mp4_free(tags, "LABEL") or _mp4_free(tags, "publisher")
    d["comment"] = g("\xa9cmt")
    cover = None
    if tags.get("covr"):
        c = tags["covr"][0]
        mime = "image/png" if getattr(c, "imageformat", 0) == MP4Cover.FORMAT_PNG else "image/jpeg"
        cover = (bytes(c), mime)
    return d, cover


def _vget(tags, *keys):
    for k in keys:
        if k in tags:
            v = _join(tags[k])
            if v:
                return v
    return ""


def _read_vorbis(f):
    tags = f.tags
    d = {}
    if tags is None:
        return d, None
    d["artist"] = _vget(tags, "artist")
    d["title"] = _vget(tags, "title")
    d["album"] = _vget(tags, "album")
    d["albumartist"] = _vget(tags, "albumartist", "album artist")
    d["genre"] = _vget(tags, "genre")
    d["year"] = _vget(tags, "date", "year")
    d["track"] = _vget(tags, "tracknumber")
    d["bpm"] = _vget(tags, "bpm", "tempo")
    d["key"] = _vget(tags, "initialkey", "key")
    d["label"] = _vget(tags, "label", "organization", "publisher")
    d["comment"] = _vget(tags, "comment", "description")
    cover = None
    pics = list(getattr(f, "pictures", []) or [])
    if not pics and "metadata_block_picture" in tags:
        for b64 in tags["metadata_block_picture"]:
            try:
                pics.append(Picture(base64.b64decode(b64)))
            except Exception:
                pass
    if pics:
        front = [p for p in pics if p.type == 3] or pics
        cover = (front[0].data, front[0].mime or guess_mime(front[0].data))
    return d, cover


def _asf_picture_parse(raw):
    try:
        ptype = raw[0]
        size = struct.unpack_from("<I", raw, 1)[0]
        pos = 5
        end = raw.index(b"\x00\x00", pos)
        while (end - pos) % 2:
            end = raw.index(b"\x00\x00", end + 1)
        mime = raw[pos:end].decode("utf-16-le")
        pos = end + 2
        end = raw.index(b"\x00\x00", pos)
        while (end - pos) % 2:
            end = raw.index(b"\x00\x00", end + 1)
        pos = end + 2
        return raw[pos:pos + size], mime, ptype
    except Exception:
        return None


def _asf_picture_build(data, mime):
    return (bytes([3]) + struct.pack("<I", len(data)) + mime.encode("utf-16-le") + b"\x00\x00"
            + b"\x00\x00" + data)


def _read_asf(tags):
    d = {}
    if tags is None:
        return d, None
    g = lambda k: _join(tags.get(k, []))
    d["artist"] = g("Author")
    d["title"] = g("Title")
    d["album"] = g("WM/AlbumTitle")
    d["albumartist"] = g("WM/AlbumArtist")
    d["genre"] = g("WM/Genre")
    d["year"] = g("WM/Year")
    d["track"] = g("WM/TrackNumber")
    d["bpm"] = g("WM/BeatsPerMinute")
    d["key"] = g("WM/InitialKey")
    d["label"] = g("WM/Publisher")
    d["comment"] = g("Description")
    cover = None
    for v in tags.get("WM/Picture", []):
        parsed = _asf_picture_parse(bytes(v.value))
        if parsed:
            cover = (parsed[0], parsed[1] or guess_mime(parsed[0]))
            break
    return d, cover


def _aget(tags, *keys):
    for k in keys:
        for tk in tags.keys():
            if tk.lower() == k.lower():
                v = tags[tk]
                if getattr(v, "kind", None) == BINARY:
                    continue
                s = str(v).replace("\x00", "; ").strip()
                if s:
                    return s
    return ""


def _read_ape(tags):
    d = {}
    if tags is None:
        return d, None
    d["artist"] = _aget(tags, "Artist")
    d["title"] = _aget(tags, "Title")
    d["album"] = _aget(tags, "Album")
    d["albumartist"] = _aget(tags, "Album Artist", "AlbumArtist")
    d["genre"] = _aget(tags, "Genre")
    d["year"] = _aget(tags, "Year", "Date")
    d["track"] = _aget(tags, "Track")
    d["bpm"] = _aget(tags, "BPM")
    d["key"] = _aget(tags, "Key", "InitialKey")
    d["label"] = _aget(tags, "Label", "Publisher")
    d["comment"] = _aget(tags, "Comment")
    cover = None
    for k in tags.keys():
        if k.lower().startswith("cover art"):
            raw = bytes(tags[k].value)
            if b"\x00" in raw:
                data = raw.split(b"\x00", 1)[1]
                cover = (data, guess_mime(data))
                break
    return d, cover


def _load(path):
    try:
        f = mutagen.File(path)
    except Exception as e:  # beschädigte Datei
        raise TagError(f"Datei konnte nicht gelesen werden: {e}") from e
    if f is None:
        raise TagError("Kein unterstütztes Audioformat")
    return f


def read_tags(path, with_cover=False):
    """Liest nur Tags (ohne technische Infos). Gibt (dict, cover|None) zurück."""
    f = _load(path)
    kind = _kind(f)
    if kind == "id3":
        d, cover = _read_id3(f.tags)
    elif kind == "mp4":
        d, cover = _read_mp4(f.tags)
    elif kind == "vorbis":
        d, cover = _read_vorbis(f)
    elif kind == "asf":
        d, cover = _read_asf(f.tags)
    elif kind == "ape":
        d, cover = _read_ape(f.tags)
    else:
        d, cover = {}, None
    for k in TAG_FIELDS:
        d.setdefault(k, "")
    return (d, cover) if with_cover else (d, None)


def read_cover(path):
    try:
        return read_tags(path, with_cover=True)[1]
    except TagError:
        return None


def read_track(path):
    """Liest Datei vollständig ein und erzeugt ein Track-Objekt (ohne id)."""
    st = os.stat(path)
    f = _load(path)
    ext = os.path.splitext(path)[1].lower()
    fmt = format_for_extension(ext) or "?"
    info = f.info
    codec = str(getattr(info, "codec", "") or "").lower()
    if fmt == "AAC" and "alac" in codec:
        fmt = "ALAC"
    if isinstance(f, MP4) and getattr(info, "length", 0) and _mp4_has_video(f):
        raise TagError("Videodatei – übersprungen")

    kind = _kind(f)
    if kind == "id3":
        d, cover = _read_id3(f.tags)
    elif kind == "mp4":
        d, cover = _read_mp4(f.tags)
    elif kind == "vorbis":
        d, cover = _read_vorbis(f)
    elif kind == "asf":
        d, cover = _read_asf(f.tags)
    elif kind == "ape":
        d, cover = _read_ape(f.tags)
    else:
        d, cover = {}, None

    length = float(getattr(info, "length", 0) or 0)
    bitrate = int(getattr(info, "bitrate", 0) or 0)
    if not bitrate and length > 0:
        bitrate = int(st.st_size * 8 / length)
    samplerate = int(getattr(info, "sample_rate", 0) or 0)
    bits = int(getattr(info, "bits_per_sample", 0) or getattr(info, "bits_per_raw_sample", 0) or 0)
    channels = int(getattr(info, "channels", 0) or 0)

    if not (d.get("artist") and d.get("title")) and fmt in ("WAV", "AIFF"):
        for k, v in read_chunk_info(path, fmt).items():
            if v and not d.get(k):
                d[k] = v
    if fmt == "OPUS" and not samplerate:
        samplerate = 48000

    tags_missing = not (d.get("artist") and d.get("title"))
    artist, title = d.get("artist", ""), d.get("title", "")
    if tags_missing:
        fa, ft = parse_filename(path)
        artist = artist or fa
        title = title or ft

    return Track(
        path=path, size=st.st_size, mtime=st.st_mtime, fmt=fmt,
        artist=artist, title=title, album=d.get("album", ""),
        albumartist=d.get("albumartist", ""), genre=d.get("genre", ""),
        year=d.get("year", ""), track=d.get("track", ""), bpm=parse_bpm(d.get("bpm")),
        key=d.get("key", ""), label=d.get("label", ""), comment=d.get("comment", ""),
        duration=length, bitrate=bitrate, samplerate=samplerate, bits=bits,
        channels=channels, lossless=get_format(fmt).lossless, has_cover=cover is not None,
        tags_missing=tags_missing, missing=False, error="",
    )


_RIFF_INFO = {b"IART": "artist", b"INAM": "title", b"IPRD": "album", b"IGNR": "genre",
              b"ICRD": "year", b"ICMT": "comment", b"ITRK": "track", b"IPRT": "track"}
_AIFF_TEXT = {b"NAME": "title", b"AUTH": "artist", b"ANNO": "comment"}


def read_chunk_info(path, fmt):
    """Liest RIFF-INFO (WAV) bzw. NAME/AUTH-Chunks (AIFF) als Rückfallebene."""
    out = {}
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
            big = fmt == "AIFF"
            if (not big and head[:4] != b"RIFF") or (big and head[:4] != b"FORM"):
                return out
            end = struct.unpack(">I" if big else "<I", head[4:8])[0] + 8
            pos = 12
            while pos + 8 <= end:
                fh.seek(pos)
                h = fh.read(8)
                if len(h) < 8:
                    break
                cid, size = h[:4], struct.unpack(">I" if big else "<I", h[4:8])[0]
                if not big and cid == b"LIST" and size < 1 << 20:
                    data = fh.read(size)
                    if data[:4] == b"INFO":
                        p = 4
                        while p + 8 <= len(data):
                            sid = data[p:p + 4]
                            ssz = struct.unpack("<I", data[p + 4:p + 8])[0]
                            val = data[p + 8:p + 8 + ssz].split(b"\x00")[0]
                            if sid in _RIFF_INFO:
                                out[_RIFF_INFO[sid]] = _decode_text(val)
                            p += 8 + ssz + (ssz & 1)
                elif big and cid in _AIFF_TEXT and size < 1 << 16:
                    out[_AIFF_TEXT[cid]] = _decode_text(fh.read(size).split(b"\x00")[0])
                pos += 8 + size + (size & 1)
    except (OSError, struct.error):
        pass
    return out


def _decode_text(b):
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _mp4_has_video(f):
    try:
        from mutagen.mp4 import Atoms
        with open(f.filename, "rb") as fh:
            atoms = Atoms(fh)
            for trak in atoms.path(b"moov")[-1].findall(b"trak"):
                try:
                    hdlr = trak[b"mdia", b"hdlr"]
                    fh.seek(hdlr.offset + 16)
                    if fh.read(4) == b"vide":
                        return True
                except KeyError:
                    pass
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
# Schreiben
# --------------------------------------------------------------------------
_KEEP = object()  # Feld nicht verändern


def _clean(v):
    return "" if v is None else str(v).strip()


def write_tags(path, values, cover=_KEEP):
    """Schreibt die angegebenen Felder. Leerer String löscht ein Feld.

    values: dict mit Teilmenge von TAG_FIELDS
    cover:  _KEEP (unverändert), None (entfernen) oder (bytes, mime)
    """
    f = _load(path)
    kind = _kind(f)
    if kind is None:
        raise TagError(f"Für {get_format(format_for_extension(os.path.splitext(path)[1]) or '?').name} "
                       "kann MOG keine Tags schreiben.")
    if f.tags is None:
        try:
            f.add_tags()
        except Exception as e:
            raise TagError(f"Tags konnten nicht angelegt werden: {e}") from e
    tags = f.tags
    values = {k: _clean(v) for k, v in values.items() if k in TAG_FIELDS}

    if kind == "id3":
        frames = {"artist": TPE1, "title": TIT2, "album": TALB, "albumartist": TPE2,
                  "genre": TCON, "year": TDRC, "track": TRCK, "bpm": TBPM, "key": TKEY,
                  "label": TPUB}
        for k, v in values.items():
            if k == "comment":
                tags.delall("COMM")
                if v:
                    tags.add(COMM(encoding=1, lang="eng", desc="", text=[v]))
                continue
            cls = frames[k]
            fid = cls.__name__
            tags.delall(fid)
            if k == "year":
                tags.delall("TYER")
            if v:
                if k == "bpm":
                    b = parse_bpm(v)
                    v = str(int(round(b))) if b else v
                tags.add(cls(encoding=1, text=[v]))
        if cover is not _KEEP:
            tags.delall("APIC")
            if cover:
                tags.add(APIC(encoding=0, mime=cover[1], type=3, desc="Cover", data=cover[0]))
        try:
            f.save(v2_version=3)
        except TypeError:
            f.save()
        return

    if kind == "mp4":
        simple = {"artist": "\xa9ART", "title": "\xa9nam", "album": "\xa9alb",
                  "albumartist": "aART", "genre": "\xa9gen", "year": "\xa9day",
                  "comment": "\xa9cmt"}
        free = {"key": "initialkey", "label": "LABEL"}
        for k, v in values.items():
            if k in simple:
                if v:
                    tags[simple[k]] = [v]
                else:
                    tags.pop(simple[k], None)
            elif k in free:
                name = f"----:com.apple.iTunes:{free[k]}"
                if v:
                    tags[name] = [MP4FreeForm(v.encode("utf-8"))]
                else:
                    tags.pop(name, None)
            elif k == "track":
                m = re.match(r"\s*(\d+)\s*(?:/\s*(\d+))?", v or "")
                if m:
                    tags["trkn"] = [(int(m.group(1)), int(m.group(2) or 0))]
                else:
                    tags.pop("trkn", None)
            elif k == "bpm":
                b = parse_bpm(v)
                if b:
                    tags["tmpo"] = [int(round(b))]
                    tags["----:com.apple.iTunes:BPM"] = [MP4FreeForm(v.encode("utf-8"))]
                else:
                    tags.pop("tmpo", None)
                    tags.pop("----:com.apple.iTunes:BPM", None)
        if cover is not _KEEP:
            if cover:
                fmt = MP4Cover.FORMAT_PNG if cover[1] == "image/png" else MP4Cover.FORMAT_JPEG
                tags["covr"] = [MP4Cover(cover[0], imageformat=fmt)]
            else:
                tags.pop("covr", None)
        f.save()
        return

    if kind == "vorbis":
        names = {"artist": "ARTIST", "title": "TITLE", "album": "ALBUM",
                 "albumartist": "ALBUMARTIST", "genre": "GENRE", "year": "DATE",
                 "track": "TRACKNUMBER", "bpm": "BPM", "key": "INITIALKEY", "label": "LABEL",
                 "comment": "COMMENT"}
        aliases = {"key": ["KEY"], "label": ["ORGANIZATION", "PUBLISHER"], "year": ["YEAR"],
                   "comment": ["DESCRIPTION"], "albumartist": ["ALBUM ARTIST"], "bpm": ["TEMPO"]}
        for k, v in values.items():
            for n in [names[k]] + aliases.get(k, []):
                if n in tags:
                    del tags[n]
            if v:
                tags[names[k]] = [v]
        if cover is not _KEEP:
            if isinstance(f, FLAC):
                f.clear_pictures()
                if cover:
                    f.add_picture(_make_picture(cover))
            else:
                if "METADATA_BLOCK_PICTURE" in tags:
                    del tags["METADATA_BLOCK_PICTURE"]
                if cover:
                    pic = _make_picture(cover)
                    tags["METADATA_BLOCK_PICTURE"] = [base64.b64encode(pic.write()).decode("ascii")]
        f.save()
        return

    if kind == "asf":
        names = {"artist": "Author", "title": "Title", "album": "WM/AlbumTitle",
                 "albumartist": "WM/AlbumArtist", "genre": "WM/Genre", "year": "WM/Year",
                 "track": "WM/TrackNumber", "bpm": "WM/BeatsPerMinute", "key": "WM/InitialKey",
                 "label": "WM/Publisher", "comment": "Description"}
        for k, v in values.items():
            if v:
                tags[names[k]] = [v]
            elif names[k] in tags:
                del tags[names[k]]
        if cover is not _KEEP:
            if "WM/Picture" in tags:
                del tags["WM/Picture"]
            if cover:
                tags["WM/Picture"] = [ASFByteArrayAttribute(_asf_picture_build(cover[0], cover[1]))]
        f.save()
        return

    if kind == "ape":
        names = {"artist": "Artist", "title": "Title", "album": "Album",
                 "albumartist": "Album Artist", "genre": "Genre", "year": "Year",
                 "track": "Track", "bpm": "BPM", "key": "Key", "label": "Label",
                 "comment": "Comment"}
        for k, v in values.items():
            for tk in list(tags.keys()):
                if tk.lower() == names[k].lower():
                    del tags[tk]
            if v:
                tags[names[k]] = v
        if cover is not _KEEP:
            for tk in list(tags.keys()):
                if tk.lower().startswith("cover art"):
                    del tags[tk]
            if cover:
                ext = "png" if cover[1] == "image/png" else "jpg"
                tags["Cover Art (Front)"] = APEValue(f"cover.{ext}".encode() + b"\x00" + cover[0], BINARY)
        f.save()
        return


def _make_picture(cover):
    pic = Picture()
    pic.type = 3
    pic.mime = cover[1]
    pic.desc = "Cover"
    pic.data = cover[0]
    try:
        from PIL import Image  # optional
        import io
        im = Image.open(io.BytesIO(cover[0]))
        pic.width, pic.height = im.size
        pic.depth = 24
    except Exception:
        pass
    return pic


def can_write(path):
    try:
        return _kind(_load(path)) is not None
    except TagError:
        return False


def copy_tags(src, dst):
    """Überträgt alle Felder und das Cover von src nach dst (z. B. nach Konvertierung)."""
    d, cover = read_tags(src, with_cover=True)
    if not can_write(dst):
        return False
    write_tags(dst, d, cover=cover if cover else _KEEP)
    return True


KEEP = _KEEP
