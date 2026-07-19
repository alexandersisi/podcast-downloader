#!/usr/bin/env python3
"""
Podcast Downloader – Suche, durchstöbere und lade Podcast-Episoden herunter.

Nutzt die iTunes Search API zum Finden von Podcasts und lädt Episoden
direkt über deren RSS-Feeds als MP3 herunter.
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    import feedparser
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    from rich.prompt import Prompt, IntPrompt, Confirm
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
except ImportError:
    print("❌ Abhängigkeiten fehlen. Bitte zuerst setup.sh ausführen.")
    print("   ./setup.sh")
    sys.exit(1)

console = Console()

# ─── Konfiguration ───────────────────────────────────────────────────────────

DEFAULT_DOWNLOAD_DIR = Path.home() / "Podcasts"
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
MAX_CONCURRENT_DOWNLOADS = 3
DEFAULT_WHISPER_MODEL = "small"  # tiny/base/small/medium/large
DEFAULT_WHISPER_LANGUAGE = "de"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Entfernt ungültige Zeichen aus Dateinamen."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:200]  # Max Länge begrenzen


def format_pub_date(pub_date: str) -> str:
    """Parst RSS-Datum und gibt YYYY-MM-DD zurück. Leer, wenn nicht parsebar."""
    if not pub_date:
        return ""
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(pub_date[:len(fmt) + 2], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def format_duration(seconds: int | None) -> str:
    """Formatiert Sekunden in lesbare Dauer."""
    if not seconds:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def format_size(size_bytes: int | None) -> str:
    """Formatiert Bytes in lesbare Größe."""
    if not size_bytes:
        return "—"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ─── Podcast-Suche ───────────────────────────────────────────────────────────

def search_podcasts(query: str, limit: int = 10) -> list[dict]:
    """Sucht Podcasts über die iTunes Search API."""
    params = {
        "term": query,
        "media": "podcast",
        "limit": limit,
        "country": "DE",
        "lang": "de_de",
    }
    try:
        resp = requests.get(ITUNES_SEARCH_URL, params=params, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "name": r.get("collectionName", "Unbekannt"),
                "artist": r.get("artistName", "Unbekannt"),
                "feed_url": r.get("feedUrl", ""),
                "episode_count": r.get("trackCount", 0),
                "artwork": r.get("artworkUrl100", ""),
                "genre": ", ".join(r.get("genres", [])),
            }
            for r in results
            if r.get("feedUrl")
        ]
    except requests.RequestException as e:
        console.print(f"[red]Fehler bei der Suche: {e}[/red]")
        return []


# ─── RSS Feed Parsing ─────────────────────────────────────────────────────────

def parse_feed(feed_url: str) -> tuple[dict, list[dict]]:
    """Parst den RSS-Feed und gibt Podcast-Info + Episoden zurück."""
    console.print(f"\n[dim]Lade Feed: {feed_url}[/dim]")

    feed = feedparser.parse(feed_url)

    podcast_info = {
        "title": feed.feed.get("title", "Unbekannt"),
        "description": feed.feed.get("subtitle", feed.feed.get("summary", "")),
        "author": feed.feed.get("author", "Unbekannt"),
        "link": feed.feed.get("link", ""),
    }

    episodes = []
    for entry in feed.entries:
        # Audio-URL finden
        audio_url = None
        audio_size = None
        audio_type = None

        for enclosure in entry.get("enclosures", []):
            if "audio" in enclosure.get("type", "") or enclosure.get("href", "").endswith((".mp3", ".m4a", ".ogg")):
                audio_url = enclosure.get("href")
                audio_size = int(enclosure.get("length", 0)) if enclosure.get("length") else None
                audio_type = enclosure.get("type", "")
                break

        # Alternativ: Links durchsuchen
        if not audio_url:
            for link in entry.get("links", []):
                if "audio" in link.get("type", ""):
                    audio_url = link.get("href")
                    break

        if not audio_url:
            continue

        # Dauer parsen
        duration_str = entry.get("itunes_duration", "")
        duration_secs = None
        if duration_str:
            try:
                parts = str(duration_str).split(":")
                if len(parts) == 3:
                    duration_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:
                    duration_secs = int(parts[0]) * 60 + int(parts[1])
                else:
                    duration_secs = int(parts[0])
            except (ValueError, IndexError):
                pass

        # Veröffentlichungsdatum
        pub_date = entry.get("published", "")

        episodes.append({
            "title": entry.get("title", "Ohne Titel"),
            "description": entry.get("summary", ""),
            "url": audio_url,
            "size": audio_size,
            "type": audio_type,
            "duration": duration_secs,
            "pub_date": pub_date,
            "episode_num": entry.get("itunes_episode", ""),
            "season_num": entry.get("itunes_season", ""),
        })

    return podcast_info, episodes


# ─── Download-Funktionen ─────────────────────────────────────────────────────

def download_episode(episode: dict, download_dir: Path, progress, task_id) -> bool:
    """Lädt eine einzelne Episode herunter."""
    url = episode["url"]

    # Dateinamen erstellen
    ext = ".mp3"
    parsed_url = urlparse(url)
    url_path = parsed_url.path
    if "." in url_path.split("/")[-1]:
        ext = "." + url_path.split("/")[-1].rsplit(".", 1)[-1]

    date_prefix = format_pub_date(episode.get("pub_date", ""))
    ep_prefix = ""
    if episode.get("season_num") and episode.get("episode_num"):
        ep_prefix = f"S{episode['season_num']:>02s}E{episode['episode_num']:>02s} - "
    elif episode.get("episode_num"):
        ep_prefix = f"E{episode['episode_num']:>02s} - "

    base = sanitize_filename(f"{ep_prefix}{episode['title']}")
    filename = (f"{date_prefix} - " if date_prefix else "") + base + ext
    filepath = download_dir / filename

    # Bereits heruntergeladen?
    if filepath.exists():
        existing_size = filepath.stat().st_size
        if episode.get("size") and abs(existing_size - episode["size"]) < 1024:
            progress.update(task_id, description=f"[dim]⏭  {episode['title'][:40]}… (existiert)[/dim]")
            progress.update(task_id, completed=episode.get("size", 0))
            return True

    try:
        resp = requests.get(url, stream=True, headers=HTTP_HEADERS, timeout=30)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0)) or episode.get("size", 0)
        if total:
            progress.update(task_id, total=total)

        downloaded = 0
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                progress.update(task_id, completed=downloaded)

        return True
    except Exception as e:
        progress.update(task_id, description=f"[red]✗ {episode['title'][:40]}… Fehler[/red]")
        console.print(f"[red]  Fehler bei {episode['title']}: {e}[/red]")
        if filepath.exists():
            filepath.unlink()
        return False


def episode_filepath(episode: dict, download_dir: Path) -> Path:
    """Berechnet den Zielpfad einer Episode (gleiche Logik wie download_episode)."""
    url = episode["url"]
    ext = ".mp3"
    parsed_url = urlparse(url)
    url_path = parsed_url.path
    if "." in url_path.split("/")[-1]:
        ext = "." + url_path.split("/")[-1].rsplit(".", 1)[-1]

    date_prefix = format_pub_date(episode.get("pub_date", ""))
    ep_prefix = ""
    if episode.get("season_num") and episode.get("episode_num"):
        ep_prefix = f"S{episode['season_num']:>02s}E{episode['episode_num']:>02s} - "
    elif episode.get("episode_num"):
        ep_prefix = f"E{episode['episode_num']:>02s} - "

    base = sanitize_filename(f"{ep_prefix}{episode['title']}")
    filename = (f"{date_prefix} - " if date_prefix else "") + base + ext
    return download_dir / filename


def transcribe_file(audio_path: Path, model_name: str, language: str | None) -> bool:
    """Transkribiert eine Audiodatei mit Whisper. Schreibt .txt und .srt daneben."""
    txt_path = audio_path.with_suffix(".txt")
    if txt_path.exists():
        console.print(f"[dim]⏭  Transkript existiert: {txt_path.name}[/dim]")
        return True

    if not shutil.which("ffmpeg"):
        console.print("[red]✗ ffmpeg fehlt. Bitte installieren: brew install ffmpeg[/red]")
        return False

    try:
        import whisper  # type: ignore
    except ImportError:
        console.print("[red]✗ openai-whisper fehlt. Bitte setup.sh erneut ausführen.[/red]")
        return False

    console.print(f"[cyan]🎙️  Transkribiere ({model_name}): {audio_path.name}[/cyan]")
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path), language=language, verbose=False)
    except Exception as e:
        console.print(f"[red]✗ Whisper-Fehler bei {audio_path.name}: {e}[/red]")
        return False

    txt_path.write_text(result.get("text", "").strip() + "\n", encoding="utf-8")

    srt_path = audio_path.with_suffix(".srt")
    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(result.get("segments", []), 1):
            f.write(f"{i}\n{_srt_ts(seg['start'])} --> {_srt_ts(seg['end'])}\n{seg['text'].strip()}\n\n")

    console.print(f"[green]✓ Transkript: {txt_path.name}[/green]")
    return True


def _srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def download_episodes(
    episodes: list[dict],
    download_dir: Path,
    transcribe: bool = False,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    whisper_language: str | None = DEFAULT_WHISPER_LANGUAGE,
):
    """Lädt mehrere Episoden mit Fortschrittsanzeige herunter."""
    download_dir.mkdir(parents=True, exist_ok=True)

    total_size = sum(e.get("size", 0) for e in episodes)
    console.print(f"\n[bold green]📥 Starte Download von {len(episodes)} Episoden[/bold green]")
    if total_size:
        console.print(f"[dim]   Geschätzte Gesamtgröße: {format_size(total_size)}[/dim]")
    console.print(f"[dim]   Zielordner: {download_dir}[/dim]")
    if transcribe:
        console.print(f"[dim]   Transkription: Whisper-Modell '{whisper_model}' ({whisper_language or 'auto'})[/dim]")
    console.print()

    success_count = 0
    fail_count = 0
    downloaded_paths: list[Path] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        for i, episode in enumerate(episodes, 1):
            desc = f"[cyan]({i}/{len(episodes)})[/cyan] {episode['title'][:45]}…"
            task_id = progress.add_task(desc, total=episode.get("size", 0) or None)

            if download_episode(episode, download_dir, progress, task_id):
                success_count += 1
                downloaded_paths.append(episode_filepath(episode, download_dir))
            else:
                fail_count += 1

    if transcribe and downloaded_paths:
        console.print(f"\n[bold cyan]🎙️  Starte Transkription von {len(downloaded_paths)} Episoden[/bold cyan]")
        for path in downloaded_paths:
            if path.exists():
                transcribe_file(path, whisper_model, whisper_language)

    # Zusammenfassung
    console.print()
    if fail_count == 0:
        console.print(Panel(
            f"[bold green]✅ Alle {success_count} Episoden erfolgreich heruntergeladen![/bold green]\n"
            f"[dim]Gespeichert in: {download_dir}[/dim]",
            title="Fertig",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[green]✅ {success_count} erfolgreich[/green]  ·  [red]✗ {fail_count} fehlgeschlagen[/red]\n"
            f"[dim]Gespeichert in: {download_dir}[/dim]",
            title="Fertig",
            border_style="yellow",
        ))


# ─── Interaktive Menüs ──────────────────────────────────────────────────────

def display_search_results(results: list[dict]) -> int | None:
    """Zeigt Suchergebnisse als Tabelle und gibt die Auswahl zurück."""
    if not results:
        console.print("[yellow]Keine Podcasts gefunden.[/yellow]")
        return None

    table = Table(
        title="🔍 Suchergebnisse",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold magenta",
    )
    table.add_column("#", style="bold cyan", width=3, justify="right")
    table.add_column("Podcast", style="bold white", max_width=40)
    table.add_column("Autor", style="dim", max_width=25)
    table.add_column("Genre", style="dim", max_width=20)
    table.add_column("Episoden", style="green", justify="right", width=8)

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r["name"],
            r["artist"],
            r["genre"],
            str(r["episode_count"]),
        )

    console.print(table)

    choice = Prompt.ask(
        "\n[bold]Podcast auswählen[/bold] (Nummer oder 'q' zum Abbrechen)",
        default="1",
    )

    if choice.lower() == "q":
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(results):
            return idx
    except ValueError:
        pass

    console.print("[red]Ungültige Auswahl.[/red]")
    return None


def display_episodes(podcast_info: dict, episodes: list[dict]) -> list[dict]:
    """Zeigt Episodenliste und ermöglicht Auswahl."""
    console.print(Panel(
        f"[bold]{podcast_info['title']}[/bold]\n"
        f"[dim]{podcast_info['author']}[/dim]\n\n"
        f"{podcast_info.get('description', '')[:200]}",
        title="🎙️  Podcast-Info",
        border_style="magenta",
    ))

    if not episodes:
        console.print("[yellow]Keine herunterladbaren Episoden gefunden.[/yellow]")
        return []

    table = Table(
        title=f"📋 {len(episodes)} Episoden verfügbar",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold cyan",
    )
    table.add_column("#", style="bold cyan", width=4, justify="right")
    table.add_column("Titel", style="white", max_width=50)
    table.add_column("Dauer", style="dim", width=8, justify="right")
    table.add_column("Größe", style="dim", width=8, justify="right")
    table.add_column("Datum", style="dim", width=16)

    # Nur die ersten 50 anzeigen, wenn es zu viele sind
    display_episodes_list = episodes[:50]
    for i, ep in enumerate(episodes, 1):
        if i <= 50:
            # Datum kürzen
            date_str = ep.get("pub_date", "")[:16]
            table.add_row(
                str(i),
                ep["title"][:50],
                format_duration(ep["duration"]),
                format_size(ep["size"]),
                date_str,
            )

    if len(episodes) > 50:
        table.add_row("…", f"[dim]… und {len(episodes) - 50} weitere Episoden[/dim]", "", "", "")

    console.print(table)

    console.print("\n[bold]Auswahl-Optionen:[/bold]")
    console.print("  [cyan]a[/cyan]     → Alle Episoden herunterladen")
    console.print("  [cyan]1-5[/cyan]   → Episoden 1 bis 5")
    console.print("  [cyan]1,3,7[/cyan] → Bestimmte Episoden")
    console.print("  [cyan]l10[/cyan]   → Die letzten 10 Episoden")
    console.print("  [cyan]q[/cyan]     → Abbrechen")

    choice = Prompt.ask("\n[bold]Episoden auswählen[/bold]", default="a")

    if choice.lower() == "q":
        return []

    if choice.lower() == "a":
        return episodes

    # "l" für letzte N Episoden
    if choice.lower().startswith("l"):
        try:
            n = int(choice[1:])
            return episodes[:n]
        except ValueError:
            pass

    # Bereichsauswahl: "1-5"
    if "-" in choice and "," not in choice:
        try:
            parts = choice.split("-")
            start = int(parts[0]) - 1
            end = int(parts[1])
            return episodes[start:end]
        except (ValueError, IndexError):
            pass

    # Einzelauswahl: "1,3,7"
    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        return [episodes[i] for i in indices if 0 <= i < len(episodes)]
    except (ValueError, IndexError):
        pass

    console.print("[red]Ungültige Auswahl, lade alle Episoden.[/red]")
    return episodes


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def interactive_mode(download_dir: Path):
    """Interaktiver Modus mit Menüführung."""
    console.print(Panel(
        "[bold magenta]🎧 Podcast Downloader[/bold magenta]\n\n"
        "Suche nach Podcasts, wähle Episoden aus und lade sie herunter.",
        border_style="magenta",
    ))

    while True:
        console.print("\n[bold]Was möchtest du tun?[/bold]")
        console.print("  [cyan]1[/cyan]  Podcast suchen")
        console.print("  [cyan]2[/cyan]  RSS-Feed-URL direkt eingeben")
        console.print("  [cyan]q[/cyan]  Beenden")

        action = Prompt.ask("\n[bold]Aktion[/bold]", choices=["1", "2", "q"], default="1")

        if action == "q":
            console.print("[dim]Auf Wiederhören! 👋[/dim]")
            break

        feed_url = None

        if action == "1":
            query = Prompt.ask("[bold]🔍 Suchbegriff[/bold]")
            if not query:
                continue

            with console.status("[bold cyan]Suche läuft…[/bold cyan]"):
                results = search_podcasts(query)

            idx = display_search_results(results)
            if idx is None:
                continue

            feed_url = results[idx]["feed_url"]

        elif action == "2":
            feed_url = Prompt.ask("[bold]🔗 RSS-Feed-URL[/bold]")
            if not feed_url:
                continue

        if not feed_url:
            continue

        # Feed laden und Episoden anzeigen
        with console.status("[bold cyan]Lade Podcast-Feed…[/bold cyan]"):
            podcast_info, episodes = parse_feed(feed_url)

        if not episodes:
            console.print("[yellow]Keine herunterladbaren Episoden in diesem Feed.[/yellow]")
            continue

        selected = display_episodes(podcast_info, episodes)

        if not selected:
            continue

        # Download-Verzeichnis
        podcast_dir = download_dir / sanitize_filename(podcast_info["title"])

        custom_dir = Prompt.ask(
            f"[bold]📁 Download-Ordner[/bold]",
            default=str(podcast_dir),
        )
        podcast_dir = Path(custom_dir)

        # Transkription?
        transcribe = Confirm.ask(
            "\n[bold]🎙️  Episoden nach Download transkribieren (Whisper)?[/bold]",
            default=False,
        )
        model_name = DEFAULT_WHISPER_MODEL
        if transcribe:
            model_name = Prompt.ask(
                "[bold]Whisper-Modell[/bold]",
                choices=["tiny", "base", "small", "medium", "large"],
                default=DEFAULT_WHISPER_MODEL,
            )

        # Bestätigung
        if Confirm.ask(
            f"\n[bold]📥 {len(selected)} Episoden nach [cyan]{podcast_dir}[/cyan] herunterladen?[/bold]",
            default=True,
        ):
            download_episodes(
                selected,
                podcast_dir,
                transcribe=transcribe,
                whisper_model=model_name,
                whisper_language=DEFAULT_WHISPER_LANGUAGE,
            )

        if not Confirm.ask("\n[bold]Weiteren Podcast herunterladen?[/bold]", default=True):
            console.print("[dim]Auf Wiederhören! 👋[/dim]")
            break


def cli_mode(args):
    """Kommandozeilen-Modus für Scripting."""
    download_dir = Path(args.output) if args.output else DEFAULT_DOWNLOAD_DIR

    if args.search:
        results = search_podcasts(args.search, limit=args.limit or 10)
        if not results:
            console.print("[yellow]Keine Ergebnisse.[/yellow]")
            sys.exit(1)

        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return

        for i, r in enumerate(results, 1):
            console.print(f"[cyan]{i}.[/cyan] [bold]{r['name']}[/bold] – {r['artist']} ({r['episode_count']} Ep.)")
            console.print(f"   [dim]Feed: {r['feed_url']}[/dim]")
        return

    if args.feed:
        podcast_info, episodes = parse_feed(args.feed)

        if args.list:
            if args.json:
                print(json.dumps(episodes, indent=2, ensure_ascii=False, default=str))
                return
            for i, ep in enumerate(episodes, 1):
                console.print(f"[cyan]{i}.[/cyan] {ep['title']} [{format_duration(ep['duration'])}]")
            return

        # Episoden auswählen
        if args.episodes == "all":
            selected = episodes
        elif args.episodes:
            try:
                if "-" in args.episodes:
                    start, end = args.episodes.split("-")
                    selected = episodes[int(start)-1:int(end)]
                else:
                    indices = [int(x)-1 for x in args.episodes.split(",")]
                    selected = [episodes[i] for i in indices]
            except (ValueError, IndexError):
                console.print("[red]Ungültige Episoden-Auswahl.[/red]")
                sys.exit(1)
        else:
            selected = episodes

        podcast_dir = download_dir / sanitize_filename(podcast_info["title"])
        download_episodes(
            selected,
            podcast_dir,
            transcribe=args.transcribe,
            whisper_model=args.whisper_model,
            whisper_language=args.whisper_language,
        )
        return


def main():
    parser = argparse.ArgumentParser(
        description="🎧 Podcast Downloader – Suche, durchstöbere und lade Podcasts herunter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s                                    Interaktiver Modus
  %(prog)s --search "Lage der Nation"          Podcast suchen
  %(prog)s --feed URL --list                   Episoden eines Feeds auflisten
  %(prog)s --feed URL --episodes 1-5           Episoden 1-5 herunterladen
  %(prog)s --feed URL --episodes all -o ~/Pod  Alle herunterladen nach ~/Pod
        """,
    )

    parser.add_argument("--search", "-s", help="Podcast nach Name suchen")
    parser.add_argument("--feed", "-f", help="RSS-Feed-URL direkt angeben")
    parser.add_argument("--episodes", "-e", help="Episoden auswählen: 'all', '1-5', '1,3,7'")
    parser.add_argument("--list", "-l", action="store_true", help="Nur Episoden auflisten, nicht herunterladen")
    parser.add_argument("--output", "-o", help=f"Download-Verzeichnis (Standard: {DEFAULT_DOWNLOAD_DIR})")
    parser.add_argument("--limit", type=int, help="Max. Suchergebnisse (Standard: 10)")
    parser.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    parser.add_argument("--transcribe", "-t", action="store_true",
                        help="Episoden nach Download mit Whisper transkribieren (.txt + .srt)")
    parser.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL,
                        choices=["tiny", "base", "small", "medium", "large"],
                        help=f"Whisper-Modell (Standard: {DEFAULT_WHISPER_MODEL})")
    parser.add_argument("--whisper-language", default=DEFAULT_WHISPER_LANGUAGE,
                        help=f"Sprache für Whisper (z.B. 'de', 'en', 'auto'). Standard: {DEFAULT_WHISPER_LANGUAGE}")

    args = parser.parse_args()

    if args.whisper_language and args.whisper_language.lower() == "auto":
        args.whisper_language = None

    # Wenn keine Argumente → interaktiver Modus
    if not args.search and not args.feed:
        interactive_mode(Path(args.output) if args.output else DEFAULT_DOWNLOAD_DIR)
    else:
        cli_mode(args)


if __name__ == "__main__":
    main()
