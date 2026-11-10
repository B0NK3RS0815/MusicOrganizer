# Änderungen

## 0.2.1
- **Behoben:** Der Knopf „Speichern“ (und „Alle Änderungen speichern“ in der Seitenleiste) hat vorgemerkte Tag-Änderungen nicht geschrieben, sondern einen Fehler ins Protokoll geschrieben. Speichern beim Beenden war nicht betroffen.
- **Behoben:** „Testton direkt“ meldete fälschlich einen Fehler, obwohl der Ton abgespielt wurde.

## 0.2.0
- **Deutlich schneller bei großen Archiven:** Laden und Sortieren von 350.000 Titeln dauert jetzt wenige Sekunden statt rund anderthalb Minuten. Die Bibliothek lädt im Hintergrund, beim Start wird nicht mehr jede Datei einzeln geprüft – nur, ob die Quelle (z. B. die SSD) angeschlossen ist.
- **Bibliothek leeren:** Bibliothek → „Bibliothek leeren …“ entfernt alle Titel und Quellen aus MOG (die Dateien bleiben unberührt). Optional lässt sich das automatische Laden beim Start abschalten (Extras → Einstellungen).
- **Tag-Änderungen werden vorgemerkt:** Änderungen aus Tag-Editor, Online-Suche und BPM-Analyse erscheinen sofort orange in der Liste und werden über „Speichern“ (Strg+S) oder beim Beenden – nach Rückfrage – in die Dateien geschrieben. Verwerfen ist jederzeit möglich.
- **Dateinamen bearbeiten (F2):** einzeln von Hand oder für viele Dateien nach Muster aus den Tags (z. B. `%artist% - %title%`), mit Vorschau und Prüfung auf ungültige Zeichen und doppelte Namen.
- **Spalten:** Breite aller Spalten frei veränderbar, Reihenfolge per Drag & Drop (z. B. Titel vor Artist) oder über das Rechtsklick-Menü im Spaltenkopf. Sortierung und Spalten werden gespeichert.
- **Beenden-Knopf** oben rechts (Strg+Q), **Versionsanzeige** neben dem Logo, „MOG by B0NK3RS“ unten rechts.
- **Update-Funktion:** MOG prüft beim Start (höchstens einmal täglich) auf neue Versionen und installiert sie auf Wunsch (Extras → Nach Updates suchen).
- **Audio-Diagnose:** Ausgabegerät wählbar, Testton, alternative Wiedergabe-Technik (Windows Media Foundation), Diagnose-Protokoll (Extras → Diagnose-Protokoll zeigen). MOG folgt jetzt auch einem Wechsel des Standard-Ausgabegeräts.

## 0.1.0
- Erste Version: Einlesen von Laufwerk/Ordner/Dateien, sortierbare Liste, Duplikatsuche mit Löschen, Tag-Editor, Online-Tags, BPM-Analyse, ffmpeg-Konverter, integrierter Player.
