# Änderungen

## 1.1.0
- **Lautstärke angleichen** (Analyse → „Lautheit messen“ und „Lautstärke angleichen …“, auch per Rechtsklick):
  - Messung nach EBU R128: integrierte Lautheit (LUFS), True Peak und Dynamik – mehrere Titel parallel. Neue Spalte „Lautheit“.
  - Zielpegel automatisch („optimal für diese Auswahl“: so laut wie möglich, ohne dass mehr als 10 % der Titel die Peak-Grenze überschreiten würden) oder fest: −9 LUFS (Club), −11, −14 (Streaming), −18 (ReplayGain) oder eigener Wert. Peak-Grenze (Standard −1 dBTP) verhindert Übersteuern; Option „nur leiser machen“.
  - Vorschau je Titel mit Änderung in dB, Ergebnis und Hinweisen, bevor etwas geändert wird.
  - Je Format der schonendste Weg: MP3 verlustfrei in 1,5-dB-Schritten (Prinzip mp3gain), WAV/AIFF direkt in der Datei, FLAC/ALAC verlustfrei neu kodiert, Opus verlustfrei über den Kopf. AAC, OGG und WMA nur auf ausdrücklichen Wunsch per Neukodierung (Qualitätsverlust).
  - Tags, Cover, Cue-Punkte und Erstellungsdatum bleiben erhalten. Optional Sicherungskopien der Originale.
  - „Pegeländerung zurücknehmen“ für verlustfrei geänderte Titel.
  - Alternativ nur ReplayGain-Tags schreiben (Dateien bleiben unverändert).
  - Hinweis, wenn betroffene Titel in rekordbox stecken (dort neu analysieren lassen).
- **rekordbox-Fenster:**
  - Neue Spalte „kbps“ (Bitrate) in der Titelliste – aus rekordbox oder, falls dort leer, aus der MOG-Bibliothek; niedrige Bitraten farbig markiert.
  - Markierte Titel in eine andere Playlist **verschieben** oder **kopieren**: Knöpfe „Verschieben nach …“/„Kopieren nach …“, Rechtsklick oder per Ziehen auf eine Playlist links (mit Strg: kopieren). Titel, die im Ziel schon stehen, werden nicht doppelt angelegt. Funktioniert mit XML und Datenbank.
- **Updates:** automatische Prüfung jetzt beim Start und regelmäßig während MOG läuft (alle 6 Stunden, täglich oder wöchentlich – Extras → Einstellungen). Neue Versionen erscheinen als Hinweis „Update“ neben der Versionsnummer und als Systembenachrichtigung; beim Start öffnet sich einmalig der Update-Dialog.
- Macs mit Apple-Chip erhalten jetzt automatisch eine eigene Version (`…-macOS-arm64.dmg`); die Update-Funktion wählt sie selbst.

## 1.0.0
- **rekordbox-Anbindung** (Knopf „rekordbox“, Strg+R) in zwei umschaltbaren Varianten:
  - **XML (offiziell, sicher):** rekordbox-XML öffnen oder neu anlegen, bearbeiten und speichern. Einlesen in rekordbox über Einstellungen → Erweitert → Datenbank → „rekordbox xml“. Cue-Punkte, Beatgrid und alle anderen Inhalte der Datei bleiben erhalten.
  - **Datenbank (direkt, inoffiziell):** bearbeitet rekordbox' eigene Bibliothek (`master.db`, rekordbox 6/7). rekordbox muss beim Speichern geschlossen sein; vor jedem Speichern legt MOG eine Sicherung an (die letzten 10 werden aufbewahrt).
  - Playlists und Ordner anlegen, umbenennen, per Drag & Drop verschieben, löschen; Titel aus MOG per Rechtsklick „Zu rekordbox hinzufügen“; Reihenfolge ändern; Titel-Infos bearbeiten (Artist, Titel, Album, Genre, Label, BPM, Tonart, Bewertung, Kommentar …).
  - Neue Spalte „rekordbox“ zeigt, in wie vielen Playlists ein Titel steckt. Umbenennen in MOG zieht den Pfad in rekordbox mit, beim Löschen warnt MOG und entfernt die Titel auf Wunsch auch aus rekordbox.
- **Tonart-Erkennung:** Analyse → „Tonart analysieren“ (oder BPM + Tonart in einem Durchgang). Anzeige als Camelot (8A), klassisch (Am) oder beides (Extras → Einstellungen); die Spalte „Tonart“ sortiert nach dem Camelot-Rad.
- **Wellenform im Player:** farbige Wellenform (Bass/Mitten/Höhen) statt Schieberegler – Klick oder Ziehen spult, wird zwischengespeichert.
- **Hell/Dunkel:** Extras → Darstellung → Dunkel, Hell oder „Wie System“ (folgt dem Systemwechsel automatisch).
- **Duplikatsuche überarbeitet:**
  - Spalten Artist, Titel, Länge, kbps, Erstellt (Erstellungsdatum der Datei), Format, rekordbox, Ordner.
  - „Automatisch markieren“ nach wählbarer Regel: beste Qualität, älteste Datei behalten, neueste Datei behalten, Titel in rekordbox bevorzugen, bevorzugter Ordner.
  - „Kein Duplikat“ blendet eine Gruppe dauerhaft aus (zurücksetzbar).
  - „Markierte verschieben“ legt Duplikate erst in einen Prüfordner, statt sie zu löschen.
  - Jede Gruppe zeigt, wie viel Platz das Löschen frei macht.
- Neues Kürzel Strg+R öffnet rekordbox.

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
