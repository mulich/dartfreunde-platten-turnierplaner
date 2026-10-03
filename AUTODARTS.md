# Autodarts auf den Board-PCs

Turnierplaner: https://turnier.mulich.de/ · Accounts und Script-Downloads:
https://dartportal.mulich.de/. Das Portal nimmt mit den angemeldeten Spieleraccounts
Einladungen der freigegebenen Board-Accounts automatisch an. Die Board-Scripts
legen private X01-Lobbys an, laden die zwei geplanten Spieler ein, ordnen beide
als lokale Spieler der Scheibe zu und übernehmen das Endergebnis in Legs.

## Container aktualisieren

Beide Anwendungen aktualisieren, jeweils im Ordner ihrer Compose-Datei:

```sh
docker compose pull
docker compose up -d
```

Für den Turnierplaner die aktualisierte `compose.server.yaml` verwenden. Sie liest
`TOURNAMENT_ADMIN_KEY` aus der Umgebung bzw. der `.env` neben der Compose-Datei.
Einen eigenen zufälligen Verwaltungsschlüssel erzeugen, beispielsweise mit
`openssl rand -hex 32`, und auf dem Server in `.env` setzen:

```dotenv
TOURNAMENT_ADMIN_KEY=HIER_DEN_EIGENEN_SCHLUESSEL_EINTRAGEN
```

Bei Portainer diese Variable in den Stack-Umgebungsvariablen setzen und den Stack
neu deployen. Den Verwaltungsschlüssel nur den Turnierverantwortlichen geben.
Er schützt Board-Kopplung, Automatik und Spielregeln; die übrige Anwendung behält
ihren bisherigen Zugriffsschutz am Reverse Proxy. Ohne diese Variable funktioniert
der manuelle Planer weiter, die Autodarts-Verwaltung ist gesperrt. Datenvolume
beibehalten; keine Datenbank oder Zugangsdaten nach GitHub hochladen.

## Einmalige Einrichtung

1. Auf jedem Scheiben-PC Tampermonkey installieren. Im Accountportal den Abschnitt
   **Turnier-Board-Scripts** öffnen und das passende Script installieren:
   - Blau: https://dartportal.mulich.de/static/turnier-blau.user.js
   - Rot: https://dartportal.mulich.de/static/turnier-rot.user.js
   - Schwarz: https://dartportal.mulich.de/static/turnier-schwarz.user.js
2. Auf dem PC bei https://play.autodarts.com/ mit dem betreffenden Board-Account
   anmelden. Die Seite nach der Installation neu laden. Ein zweites Script zur
   automatischen Lobby-Steuerung, insbesondere „Lokale Spieler“, für den Betrieb
   der Turnier-Automatik deaktivieren.
3. Im Planer **Autodarts** öffnen. Für jede Scheibe **Schlüssel erzeugen** wählen,
   den Verwaltungsschlüssel eingeben und den einmal angezeigten Board-Schlüssel
   kopieren. Im Autodarts-Fenster des passenden PCs unten rechts **Verbinden**
   wählen und diesen Board-Schlüssel einfügen. Tampermonkey muss die Verbindungen
   zu `turnier.mulich.de` und `api.autodarts.com` erlauben.
4. Jeder Teilnehmer muss mit dem exakten Autodarts-Accountnamen im Turnier stehen
   und in der bestätigten Freundesliste jedes verwendeten Board-Accounts stehen.
   Eine User-ID oder ein Vereinsname muss nicht eingegeben werden. IDs werden
   intern über die Freundesliste aufgelöst. Fehlende/mehrdeutige Namen stoppen
   die Lobby-Vorbereitung und werden als Hinweis angezeigt.
5. Im Accountportal die Spieleraccounts anmelden und die automatische Annahme
   aktivieren. Die Board-Accounts müssen dort als erlaubte Gastgeber eingetragen
   sein. Den Script-Status im Planer über **Aktualisieren** prüfen.

| Scheibe | Fest hinterlegte Board-ID |
| --- | --- |
| Blau | faa2cd5f-5d19-4e68-9749-1b7b95c753d4 |
| Rot | ad381dc0-7e86-45a1-9fa8-61c8b18ec89b |
| Schwarz | 6e390006-cdba-4ac5-b0bb-0e03eb880af6 |

## Turnier starten

Beim Erstellen X01-Startpunkte, Best of bzw. First to, Anzahl Legs, In/Out,
Bull-Wertung und maximale Runden wählen. Best of benötigt eine ungerade Zahl:
Best of 3 bedeutet 2 Legs zum Sieg. Bull-off ist immer aus; Spieler 1 im Spielplan
steht in der Lobby zuerst und wirft an. Bereits vorhandene Turniere haben keine
überlieferten Spielregeln; diese über **Spielregeln** ausdrücklich speichern,
bevor die Automatik aktiviert werden kann. Änderungen gelten für kommende Spiele.

Bestehende fremde Spiele auf den Scheiben zuerst beenden. Im gewünschten Turnier
**Autodarts starten** wählen und den Verwaltungsschlüssel eingeben. Nur ein
Turnier kann gleichzeitig automatisch laufen. Pro Scheibe nur ein aktiver Browser-Tab
mit dem passenden Script. Alle Begegnungen des aktuellen Durchgangs müssen beendet
sein, bevor der nächste Durchgang angelegt wird. Damit wird kein Spieler zeitgleich
zu zwei Spielen eingeladen.

Die Scripts warten auf beide Einladungsannahmen und prüfen Namen, Spielerreihenfolge,
Board-Zuordnung und Regeln vor dem Start. Der Planer übernimmt ausschließlich ein
bestätigtes Endergebnis aus der Match-Statistik, passend zu beiden Accounts und der
konfigurierten Anzahl Legs. Einzelne Leg-Enden und Restpunkte werden nicht als
Turnierergebnis übernommen. Während der Automatik sind manuelle Ergebnisfelder
gesperrt; Spielplan und Tabelle aktualisieren sich alle fünf Sekunden.

## Pause und Fehlerbehebung

**Autodarts pausieren** hält die Bearbeitung im Planer an. Bereits laufende
Autodarts-Matches laufen auf der Scheibe weiter; nach Fortsetzen werden deren
Ergebnisse übernommen. Auch Abbrechen/Löschen im Planer beendet das externe Match
nicht. Ein Script kann lokal mit **Start / Pause** angehalten werden.

Bei unklarer Lobby-Erstellung oder unbestätigtem Matchstart erfolgt kein weiterer
Erstellungsversuch, um doppelte Spiele zu vermeiden. Turnier-Automatik pausieren,
in Autodarts die tatsächliche Lobby bzw. das Match prüfen und beenden. Danach im
Planer unter **Autodarts → Verknüpfte Begegnungen → Zuordnung zurücksetzen** den
Auftrag zurücksetzen und die Automatik fortsetzen. Ein Zurücksetzen löscht kein
bereits gespeichertes Turnierergebnis. Einen neuen Board-Schlüssel nur bei Bedarf
erzeugen; er macht den alten ungültig und muss erneut im PC-Script eingefügt werden.

Nach einem Seiten-Neuladen kann die Übernahme der Board-Steuerung bis zu 75 Sekunden
dauern. Ein abgemeldeter Board-Account benötigt erneute Anmeldung. Der Autodarts-
Zugriffstoken bleibt im Speicher des Board-Browsers; im Planer liegen nur gehashte
Board-Schlüssel sowie Zuordnungen, Account-IDs und Ergebnisse.

Die Schnittstelle basiert auf dem aktuellen offiziellen Autodarts-Webclient und
ist keine garantierte öffentliche Automatisierungs-API. Änderungen bei Autodarts
können eine Script-Anpassung erfordern. Backend, Zustandswechsel und Script-Adapter
werden mit isolierten Fixtures getestet. Der erste reale Lobby-Start und die
Ergebnisübernahme müssen an euren Scheiben mit zwei angemeldeten Testspielern
geprüft werden; diese Tests benötigen die tatsächlichen Board-PCs.

## Entwicklung

Die drei Scripts werden aus `scripts/board-bridge.template.js` generiert:

```sh
python scripts/generate_board_scripts.py
python -m pytest -q
node --check dartabend/static/app.js
node --check dartabend/static/integration.js
```

In diesem gemeinsamen Workspace schreibt der Generator dieselben Download-Dateien
auch ins benachbarte Accountportal. In einem eigenständigen Checkout werden die
Portal-Dateien unter `../app/static` vorbereitet und müssen separat ins Portal-
Repository übernommen werden. Beide Images nach Script-Änderungen aktualisieren.
