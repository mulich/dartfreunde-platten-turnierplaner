# Dartfreunde Platten – Turnierplaner

Eigenständige Webanwendung auf Grundlage von `dart_turnierplan.py`. Deutsche,
responsive Oberfläche für Computer, Tablet und Smartphone. Das vorhandene
Autodarts-Account-Portal ist eine getrennte Anwendung.

## Funktionen

- Spielerauswahl per Ein-Klick-Shortcuts aus gespeicherten Turnieren.
  Muli, Bruce, Ly, Schlatho, Michel, Rote, Manuel und Swobi sind vorbelegt.
- Ausgewählte Teilnehmer mit dem kleinen × entfernen; der Shortcut bleibt
  für spätere Turniere verfügbar. Neue Namen können manuell hinzugefügt werden.
- Jeder-gegen-jeden-Turniere mit 2–64 Spielern und zwei oder drei Scheiben.
- Originalregeln für zufällige Paarungen, Scheibenverteilung und möglichst faire
  Anwürfe. Scheiben: Rot, Blau, optional Schwarz. Spieler 1 wirft an.
- Bei ungerader Spielerzahl ein Freilos pro Runde, in der Oberfläche als Pause
  angezeigt. Pro Durchgang spielt jeder Spieler höchstens einmal.
- Ergebnisse in Legs eingeben, speichern, korrigieren und zurücksetzen.
- Tabelle: Sieg = 2 Punkte; Sortierung nach Punkten, gewonnenen Legs,
  Leg-Differenz. Vollständig gleiche Werte teilen sich den Rang.
- Turniere nach dem letzten Ergebnis abschließen und im Archiv nachsehen.
  Für Korrekturen lassen sich abgeschlossene Turniere wieder öffnen.
- Laufende Turniere mit Bestätigungsabfrage abbrechen; bisherige Ergebnisse
  bleiben als Zwischenstand im Archiv. Abgebrochene Turniere lassen sich fortsetzen.
- Tabelle mit Medaillen für die Plätze 1–3, hervorgehobenen Punkten und Leg-Differenz.
- Archivierte Turniere mit Sicherheitsabfrage endgültig löschen.
- Alle Daten bleiben in einer SQLite-Datenbank gespeichert; kein Excel notwendig.
- Verteilung der Scheiben und Anwürfe je Spieler ansehen.
- Schutz vor Überschreiben eines inzwischen geänderten Ergebnisses: Bei einem
  Konflikt die Ansicht aktualisieren und das Ergebnis erneut prüfen.

Manuelle Ergebnisse sind ganze Zahlen von 0 bis 999 ohne Unentschieden.
Für Autodarts gelten die eingestellten X01-Regeln (Best of / First to, Legs,
Startpunkte und In/Out). Bull-off ist immer aus. Über Board-Scripts sind private
Lobbys, Einladungen und automatische Ergebnisübernahme möglich. Einrichtung:
[AUTODARTS.md](AUTODARTS.md). Während der Automatik aktualisiert sich die Ansicht
alle fünf Sekunden; manuelle Eingaben sind gesperrt. Neue Installationen starten
ohne Turniere. Bestehende Daten im Docker-Volume bleiben bei Updates erhalten.

## GitHub und Docker auf dem Server

Repository: https://github.com/mulich/dartfreunde-platten-turnierplaner

GitHub Actions prüft jeden Push auf `main` und baut anschließend das Docker-Image
für AMD64 und ARM64. Das Image liegt unter
`ghcr.io/mulich/dartfreunde-platten-turnierplaner:latest`.
Künftige beauftragte Codeänderungen werden nach erfolgreicher Prüfung committed
und auf GitHub veröffentlicht. Lokale Dateien werden nicht automatisch synchronisiert.

Die Datei `compose.server.yaml` auf den Server kopieren und dort als
`compose.yaml` speichern, z. B. in `/opt/dartabend`. Docker Engine mit Compose
muss vorhanden sein. Dann:

```sh
cd /opt/dartabend
docker compose up -d
```

Danach `http://SERVER-IP:18081` öffnen. In Portainer kann der Inhalt der YAML-Datei
als Stack eingefügt werden. Der Server benötigt keine Python-Installation.
Der Port unterscheidet sich vom Account-Portal (18080). Mit `TOURNAMENT_PORT`
kann der Host-Port angepasst werden; standardmäßig wird 18081 verwendet.

Updates einspielen:

```sh
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 turnierplaner
```

Der Container läuft als unprivilegierter Benutzer. SQLite liegt unter
`/data/tournaments.sqlite3` im benannten Volume
`dartfreunde-platten-turnierplaner-data`. Container-Updates und
`docker compose down` erhalten das Volume. **Nicht `down -v` verwenden**, wenn
du die Turnierdaten behalten möchtest.

Die App enthält einen Healthcheck unter `/health`. Die erste Version ist für
euer LAN/VPN ohne Benutzeranmeldung gedacht. Bei einer öffentlichen Domain
Zugriffsschutz und HTTPS am Reverse Proxy konfigurieren. Es gibt keine externen
Schriftarten, CDN-Abhängigkeiten oder Tracker.

Alternativ lokal aus dem Quellcode bauen:

```sh
git clone https://github.com/mulich/dartfreunde-platten-turnierplaner.git
cd dartfreunde-platten-turnierplaner
docker compose -f compose.yaml up -d --build
```

`compose.yaml` verwendet einen lokalen Build; `compose.server.yaml` das fertige
GitHub-Image. Beim Wechsel zwischen diesen Varianten dasselbe Datenvolume
verwenden oder vorher eine Sicherung übertragen.

## Datensicherung und Wiederherstellung

Eine konsistente Sicherung kann während des Betriebs mit der SQLite-Backup-API
angelegt werden. Im Ordner mit der `compose.yaml`:

```sh
mkdir -p backups
docker compose exec -T turnierplaner python -c "import sqlite3; src=sqlite3.connect('/data/tournaments.sqlite3'); dst=sqlite3.connect('/data/backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
docker compose cp turnierplaner:/data/backup.sqlite3 ./backups/tournaments.sqlite3
```

Jede Sicherung zusätzlich außerhalb des Servers aufbewahren. Der obige Dateiname
überschreibt die vorherige lokale Sicherung; für mehrere Stände eigene Dateinamen
verwenden.

Zur Wiederherstellung den Dienst stoppen, die Sicherungsdatei in das Volume kopieren
und die Zugriffsrechte setzen. **Dabei wird der aktuelle Datenbestand ersetzt**;
vorher ebenfalls sichern. Die Datei `./backups/tournaments.sqlite3` muss existieren.

```sh
docker compose stop turnierplaner
docker compose run --rm --no-deps --user root -v "$PWD/backups:/backup:ro" turnierplaner python -c "import shutil, os; shutil.copyfile('/backup/tournaments.sqlite3', '/data/tournaments.sqlite3'); os.chown('/data/tournaments.sqlite3', 10001, 10001)"
docker compose up -d
```

## Lokal entwickeln

Python 3.11 oder neuer. Befehle aus diesem Ordner ausführen:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn dartabend.main:app --host 127.0.0.1 --port 18081
```

Ohne Umgebungsvariable liegt die Datenbank in `data/tournaments.sqlite3` relativ
zum Arbeitsordner. Alternativ `TOURNAMENT_DB=/pfad/turniere.sqlite3` setzen.

Tests:

```sh
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest -q
```

Tests verwenden ausschließlich temporäre Datenbanken. Sie prüfen Paarungen,
Kollisionsfreiheit pro Durchgang, Wertung, Validierung, Ergebniskonflikte,
Archivierung, Wiederöffnung und Persistenz nach erneutem App-Start.

Technischer Aufbau: FastAPI, Python-Standardbibliothek `sqlite3`, statisches
HTML/CSS/JavaScript ohne Frontend-Build. Grundlagen:
[FastAPI-Container](https://fastapi.tiangolo.com/deployment/docker/) und
[SQLite in Python](https://docs.python.org/3/library/sqlite3.html).

## Historische Turniere und Löschen

Historische Turnierdaten werden nicht mehr im Repository oder Docker-Image
mitgeliefert und beim normalen Start nicht importiert. Bereits importierte
Turniere bleiben in deiner bestehenden SQLite-Datenbank erhalten.

Zum Löschen im Archiv das betreffende Turnier öffnen und „Turnier löschen“
auswählen. Nach Bestätigung werden das Turnier, seine Spielerzuordnungen und
alle zugehörigen Spiele und Ergebnisse endgültig gelöscht. Andere Turniere
bleiben erhalten. Laufende Turniere können nicht gelöscht werden.

Die acht vorbelegten Spieler-Shortcuts bleiben verfügbar. Weitere Namen stammen
aus den noch gespeicherten Turnieren. Gelöschte Imports werden als Fingerabdruck
vermerkt, damit sie auch bei einem ausdrücklich eingerichteten erneuten Import
nicht wieder erscheinen.

Die optionale Ausleseroutine `scripts/extract_excel_history.py` benötigt
`openpyxl`. Ein Import erfolgt nur, wenn `TOURNAMENT_HISTORY` ausdrücklich auf
eine extrahierte JSON-Datei gesetzt wird. Die laufende App benötigt keine
Excel-Bibliothek. Frühere Git-Commits und ältere Image-Versionen können die
ursprünglich veröffentlichten Daten weiterhin enthalten.
