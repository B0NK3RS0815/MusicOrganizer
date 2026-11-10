"""Unterstützte Audioformate und ihre Darstellung."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    key: str          # interner Schlüssel, z. B. "MP3"
    label: str        # Text im Format-Badge
    name: str         # ausgeschriebener Name
    lossless: bool
    color: str        # Badge-Farbe


FORMATS = {
    "MP3":  AudioFormat("MP3", "MP3", "MPEG-1 Layer III", False, "#F28C28"),
    "MP2":  AudioFormat("MP2", "MP2", "MPEG-1 Layer II", False, "#C9772A"),
    "AAC":  AudioFormat("AAC", "AAC", "Advanced Audio Coding", False, "#8E5CF7"),
    "ALAC": AudioFormat("ALAC", "ALAC", "Apple Lossless", True, "#B04DF0"),
    "FLAC": AudioFormat("FLAC", "FLAC", "Free Lossless Audio Codec", True, "#2BB673"),
    "WAV":  AudioFormat("WAV", "WAV", "Waveform Audio (PCM)", True, "#3B82F6"),
    "AIFF": AudioFormat("AIFF", "AIFF", "Audio Interchange File Format", True, "#14B8A6"),
    "OGG":  AudioFormat("OGG", "OGG", "Ogg Vorbis", False, "#E0B020"),
    "OPUS": AudioFormat("OPUS", "OPUS", "Opus", False, "#22B8CF"),
    "WMA":  AudioFormat("WMA", "WMA", "Windows Media Audio", False, "#6B7AA1"),
    "APE":  AudioFormat("APE", "APE", "Monkey's Audio", True, "#7C9A3A"),
    "WV":   AudioFormat("WV", "WV", "WavPack", True, "#4F9D69"),
    "MPC":  AudioFormat("MPC", "MPC", "Musepack", False, "#A0785A"),
    "DSD":  AudioFormat("DSD", "DSD", "Direct Stream Digital", True, "#D94F8A"),
    "TTA":  AudioFormat("TTA", "TTA", "True Audio", True, "#5E8C8C"),
    "SPX":  AudioFormat("SPX", "SPX", "Speex", False, "#8C8C5E"),
}

UNKNOWN = AudioFormat("?", "?", "Unbekannt", False, "#555A66")

# Dateiendung -> Formatschlüssel (".m4a" wird beim Einlesen zu AAC oder ALAC aufgelöst)
EXTENSIONS = {
    ".mp3": "MP3", ".mp2": "MP2",
    ".m4a": "AAC", ".m4b": "AAC", ".aac": "AAC", ".mp4": "AAC",
    ".alac": "ALAC",
    ".flac": "FLAC",
    ".wav": "WAV", ".wave": "WAV",
    ".aif": "AIFF", ".aiff": "AIFF", ".aifc": "AIFF",
    ".ogg": "OGG", ".oga": "OGG",
    ".opus": "OPUS",
    ".wma": "WMA",
    ".ape": "APE",
    ".wv": "WV",
    ".mpc": "MPC",
    ".dsf": "DSD", ".dff": "DSD",
    ".tta": "TTA",
    ".spx": "SPX",
}

# .mp4 nur, wenn es reine Audiodateien sind – Videos werden beim Einlesen aussortiert
AUDIO_EXTENSIONS = set(EXTENSIONS)


def get_format(key):
    return FORMATS.get(key, UNKNOWN)


def format_for_extension(ext):
    return EXTENSIONS.get(ext.lower())


def dialog_filter():
    """Dateifilter für Datei-Dialoge."""
    pats = " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS))
    return f"Audiodateien ({pats});;Alle Dateien (*)"
