# Podcast Downloader

Suche, durchstöbere und lade Podcast-Episoden herunter — optional gleich mit Whisper-Transkription.

Nutzt die iTunes Search API zum Finden von Podcasts und lädt Episoden direkt über deren RSS-Feeds als MP3 herunter.

## Features

- Podcast-Suche über die iTunes Search API
- Interaktiver Modus mit Menüführung
- CLI-Modus für Scripting
- Episodenauswahl (alle, Bereich, einzelne, letzte N)
- **Datumspräfix `YYYY-MM-DD` vor jedem Dateinamen** (aus dem RSS-`pub_date`)
- **Optionale Transkription mit OpenAI Whisper** (`.txt` + `.srt`)
- Fortschrittsanzeige beim Download
- JSON-Ausgabe für Weiterverarbeitung
- Erkennung bereits heruntergeladener Episoden und Transkripte

## Installation

```bash
./setup.sh
```

Das Setup erstellt ein Virtual Environment, installiert alle Abhängigkeiten (inkl. `openai-whisper`) und bietet an, ffmpeg via Homebrew zu installieren, falls es fehlt.

## Verwendung

### Interaktiver Modus

```bash
./run.sh
```

Fragt nach Podcast, Episodenauswahl und ob transkribiert werden soll (inkl. Whisper-Modell).

### CLI-Modus

```bash
# Podcast suchen
./run.sh --search "Lage der Nation"

# Episoden eines Feeds auflisten
./run.sh --feed <URL> --list

# Episoden 1-5 herunterladen
./run.sh --feed <URL> --episodes 1-5

# Alle Episoden herunterladen + transkribieren
./run.sh --feed <URL> --episodes all --transcribe

# Anderes Whisper-Modell und Sprache 'auto'
./run.sh --feed <URL> --episodes 1-3 --transcribe --whisper-model medium --whisper-language auto

# Download-Verzeichnis angeben
./run.sh --feed <URL> --episodes all -o ~/Podcasts

# Suchergebnisse als JSON
./run.sh --search "Podcast" --json
```

## Dateinamensschema

`YYYY-MM-DD - S01E42 - Episodentitel.mp3`

Beispiel: `2026-07-19 - E128 - KI und Führung.mp3`

Fehlt in einem Feed das Publikationsdatum, wird das Präfix weggelassen. Season/Episode-Präfix (`S01E42` bzw. `E42`) wird beibehalten, wenn im Feed vorhanden.

Transkripte landen als `.txt` und `.srt` neben der MP3 mit gleichem Basisnamen.

## Whisper-Modelle

| Modell   | Qualität     | Geschwindigkeit | RAM    |
|----------|--------------|-----------------|--------|
| `tiny`   | –            | sehr schnell    | ~1 GB  |
| `base`   | +            | schnell         | ~1 GB  |
| `small`  | ++ (Default) | mittel          | ~2 GB  |
| `medium` | +++          | langsam         | ~5 GB  |
| `large`  | ++++         | sehr langsam    | ~10 GB |

## Abhängigkeiten

- Python 3.10+
- requests, feedparser, rich
- openai-whisper
- ffmpeg (systemweit)
