# Podcast Downloader

Suche, durchstöbere und lade Podcast-Episoden herunter.

Nutzt die iTunes Search API zum Finden von Podcasts und lädt Episoden direkt über deren RSS-Feeds als MP3 herunter.

## Features

- Podcast-Suche über die iTunes Search API
- Interaktiver Modus mit Menüführung
- CLI-Modus für Scripting
- Episodenauswahl (alle, Bereich, einzelne, letzte N)
- Fortschrittsanzeige beim Download
- JSON-Ausgabe für Weiterverarbeitung
- Erkennung bereits heruntergeladener Episoden

## Installation

```bash
./setup.sh
```

Das Setup erstellt ein Virtual Environment und installiert alle Abhängigkeiten.

## Verwendung

### Interaktiver Modus

```bash
./run.sh
```

### CLI-Modus

```bash
# Podcast suchen
./run.sh --search "Lage der Nation"

# Episoden eines Feeds auflisten
./run.sh --feed <URL> --list

# Episoden 1-5 herunterladen
./run.sh --feed <URL> --episodes 1-5

# Alle Episoden herunterladen
./run.sh --feed <URL> --episodes all

# Download-Verzeichnis angeben
./run.sh --feed <URL> --episodes all -o ~/Podcasts

# Suchergebnisse als JSON
./run.sh --search "Podcast" --json
```

## Abhängigkeiten

- Python 3.10+
- requests
- feedparser
- rich
