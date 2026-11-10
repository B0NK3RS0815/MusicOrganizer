"""Kerntests ohne Oberfläche. Aufruf: python tests/test_core.py <samples-ordner>"""
import glob
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mog.core import encoder, fileops, tags  # noqa: E402

samples = sys.argv[1]
work = tempfile.mkdtemp()
shutil.copytree(samples, os.path.join(work, "s"))
files = [f for f in glob.glob(os.path.join(work, "s", "**", "*.*"), recursive=True)
         if not os.path.basename(f).startswith("._")]

# winziges PNG als Cover
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360f8cf00000301010018dd8db40000000049454e44ae426082")
ok = fail = 0
vals = {"artist": "Testartist", "title": "Testtitel – Ümlaut", "album": "Album X", "genre": "Tech House",
        "year": "2025", "bpm": "126", "key": "8A", "label": "MOG Records", "comment": "Kommentar",
        "albumartist": "Various", "track": "3"}
for f in sorted(files):
    name = os.path.basename(f)
    try:
        tags.write_tags(f, vals, cover=(PNG, "image/png"))
        d, cov = tags.read_tags(f, with_cover=True)
        bad = [k for k, v in vals.items() if (d.get(k) or "").split("/")[0] != v]
        if bad or not cov:
            print(f"  ✗ {name}: falsch gelesen {bad} cover={bool(cov)} -> {[d.get(k) for k in bad]}")
            fail += 1
        else:
            print(f"  ✓ {name}")
            ok += 1
    except Exception as e:
        print(f"  ✗ {name}: {type(e).__name__}: {e}")
        fail += 1
print(f"Tags: {ok} ok, {fail} Fehler")

ff = encoder.find_ffmpeg()
flac = [f for f in files if f.endswith(".flac")][0]
for key in ("mp3_320", "aac_256", "aiff16", "wav16", "flac", "opus_192", "ogg_q8", "alac"):
    p = encoder.PRESETS_BY_KEY[key]
    dst = encoder.unique_path(os.path.join(work, "out", "conv_" + key + p.ext))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    prog = []
    encoder.convert(ff, flac, dst, p, duration=40, progress=prog.append)
    tags.copy_tags(flac, dst)
    t = tags.read_track(dst)
    d, cov = tags.read_tags(dst, with_cover=True)
    print(f"  ✓ {key:9} -> {t.fmt:5} {t.bitrate // 1000:5} kbps  {t.duration:.1f}s  "
          f"artist={d['artist']!r} bpm={d['bpm']} cover={bool(cov)} progress={len(prog)}")
    assert d["artist"] == "Testartist" and abs(t.duration - 40) < 0.5

victim = os.path.join(work, "out", "conv_mp3_320.mp3")
okd, msg = fileops.delete_file(victim, permanent=True)
assert okd and not os.path.exists(victim)
print("Löschen ✓")
shutil.rmtree(work)
print("Kerntests OK" if fail == 0 else "Kerntests mit Fehlern")
sys.exit(1 if fail else 0)
