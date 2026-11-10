"""Erzeugt das MOG-Logo (App-Icon + Wortmarke) als SVG.

Die Buchstaben werden aus der Schrift Sora (SIL OFL) in Pfade umgewandelt,
damit das Logo auf jedem System identisch aussieht.
"""
import math
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONTS = Path(__file__).resolve().parent.parent / "fonts"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "logo_out")
OUT.mkdir(parents=True, exist_ok=True)

ORANGE = "#FF8A1F"
PINK = "#FF2E6E"
VIOLET = "#9B3BFF"


def text_path(text, font_file, size, x, y, tracking=0.0):
    """Gibt (svg_path_d, breite) für Text zurück; y = Grundlinie."""
    font = TTFont(font_file)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    pen = SVGPathPen(gs)
    cursor = 0.0
    for ch in text:
        gname = cmap[ord(ch)]
        glyph = gs[gname]
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x + cursor, y))
        glyph.draw(tpen)
        cursor += glyph.width * scale + tracking
    return pen.getCommands(), cursor - tracking


def glyph_width(ch, font_file, size):
    font = TTFont(font_file)
    gs = font.getGlyphSet()
    g = gs[font.getBestCmap()[ord(ch)]]
    return g.width * size / font["head"].unitsPerEm


def vinyl(cx, cy, r, uid, label_text=None, groove_color="#FFFFFF", disc="#121318",
          hole_color="#121318", detail=True, rim_light=0.0):
    """Schallplatte als SVG-Gruppe."""
    lr = r * 0.42  # Label-Radius
    parts = [f"""
  <defs>
    <linearGradient id="lab{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{ORANGE}"/>
      <stop offset="0.55" stop-color="{PINK}"/>
      <stop offset="1" stop-color="{VIOLET}"/>
    </linearGradient>
    <radialGradient id="disc{uid}" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0.40" stop-color="#1E2028"/>
      <stop offset="1" stop-color="{disc}"/>
    </radialGradient>
    <linearGradient id="sheen{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.0"/>
      <stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0.16"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0.0"/>
    </linearGradient>
    <clipPath id="clip{uid}"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>
  </defs>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#disc{uid})"/>"""]
    if detail:
        # Rillen
        g = []
        n = 0
        rr = lr + r * 0.06
        while rr < r * 0.96:
            op = 0.05 + 0.04 * (n % 3 == 0)
            g.append(f'<circle cx="{cx}" cy="{cy}" r="{rr:.2f}" fill="none" '
                     f'stroke="{groove_color}" stroke-opacity="{op:.2f}" stroke-width="{r*0.006:.2f}"/>')
            rr += r * 0.032
            n += 1
        parts.append("  " + "\n  ".join(g))
        # Lichtreflex (zwei gegenüberliegende Keile)
        def wedge(a0, a1):
            x0 = cx + r * math.cos(math.radians(a0)); y0 = cy + r * math.sin(math.radians(a0))
            x1 = cx + r * math.cos(math.radians(a1)); y1 = cy + r * math.sin(math.radians(a1))
            return f"M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 0 1 {x1:.2f},{y1:.2f} Z"
        parts.append(f'  <g clip-path="url(#clip{uid})" opacity="0.9">'
                     f'<path d="{wedge(-75, -40)}" fill="url(#sheen{uid})"/>'
                     f'<path d="{wedge(105, 140)}" fill="url(#sheen{uid})"/></g>')
    parts.append(f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#000" '
                 f'stroke-opacity="0.55" stroke-width="{r*0.015:.2f}"/>')
    if rim_light:
        parts.append(f'  <circle cx="{cx}" cy="{cy}" r="{r - r*0.012:.2f}" fill="none" stroke="#FFFFFF" '
                     f'stroke-opacity="{rim_light}" stroke-width="{r*0.025:.2f}"/>')
    parts.append(f'  <circle cx="{cx}" cy="{cy}" r="{lr:.2f}" fill="url(#lab{uid})"/>')
    if label_text:
        size = lr * 0.62
        w = sum(glyph_width(c, FONTS / "Sora-800.ttf", size) for c in label_text) + size * 0.02 * (len(label_text) - 1)
        d, _ = text_path(label_text, FONTS / "Sora-800.ttf", size, cx - w / 2, cy + size * 0.36, tracking=size * 0.02)
        parts.append(f'  <path d="{d}" fill="#FFFFFF"/>')
        # kleine Spindel unterhalb des Schriftzugs
        parts.append(f'  <circle cx="{cx}" cy="{cy + lr*0.62:.2f}" r="{lr*0.07:.2f}" fill="{hole_color}"/>')
    else:
        parts.append(f'  <circle cx="{cx}" cy="{cy}" r="{lr*0.16:.2f}" fill="{hole_color}"/>')
    return "\n".join(parts)


def icon_svg():
    s = 1024
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">
  <title>MusicOrganizer (MOG)</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2A2C38"/>
      <stop offset="1" stop-color="#0D0E13"/>
    </linearGradient>
  </defs>
  <rect x="40" y="40" width="944" height="944" rx="212" fill="url(#bg)"/>
  <rect x="40" y="40" width="944" height="944" rx="212" fill="none" stroke="#FFFFFF" stroke-opacity="0.07" stroke-width="3"/>
{vinyl(512, 512, 380, "i", label_text="MOG", hole_color="#1A1B22")}
</svg>
"""


def wordmark_svg(dark_bg=True):
    """Querformat: M (Vinyl) G + 'MusicOrganizer'."""
    fg = "#F3F3F6" if dark_bg else "#14151A"
    sub = "#9A9CAA" if dark_bg else "#5A5C68"
    bold = FONTS / "Sora-800.ttf"
    reg = FONTS / "Sora-400.ttf"
    size = 120
    base = 112          # Grundlinie
    cap = size * 0.70   # ungefähre Versalhöhe Sora
    x = 8
    dM, wM = text_path("M", bold, size, x, base)
    x += wM + 6
    r = cap / 2 + 7
    vcx = x + r
    vcy = base - cap / 2
    vin = vinyl(vcx, vcy, r, "w", label_text=None, hole_color="#121318" if dark_bg else "#FFFFFF",
                detail=True, rim_light=0.22 if dark_bg else 0.0)
    x = vcx + r + 6
    dG, wG = text_path("G", bold, size, x, base)
    x += wG
    # Untertitel rechts, zweizeilig wirkt in der Kopfzeile zu hoch -> einzeilig daneben
    sx = x + 26
    dS, wS = text_path("MusicOrganizer", reg, 34, sx, base - cap / 2 + 12, tracking=0.6)
    width = sx + wS + 8
    height = 132
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height}" viewBox="0 0 {width:.0f} {height}">
  <title>MusicOrganizer (MOG)</title>
  <path d="{dM}" fill="{fg}"/>
{vin}
  <path d="{dG}" fill="{fg}"/>
  <rect x="{x + 12:.1f}" y="{vcy - 22:.1f}" width="2" height="44" rx="1" fill="{sub}" opacity="0.6"/>
  <path d="{dS}" fill="{sub}"/>
</svg>
"""


(OUT / "mog_icon.svg").write_text(icon_svg(), encoding="utf-8")
(OUT / "mog_wordmark_dark.svg").write_text(wordmark_svg(True), encoding="utf-8")
(OUT / "mog_wordmark_light.svg").write_text(wordmark_svg(False), encoding="utf-8")
print("Logos geschrieben nach", OUT)
