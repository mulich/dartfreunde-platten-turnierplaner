# Autodarts: Spieleraccounts und lokale Gäste

## Notfall: Lobby neu starten (2.4.0)

Im Autodarts-Reiter bei einer bestätigten, noch nicht gestarteten Lobby
**Notfall: Lobby neu starten** wählen und die konkrete Begegnung bestätigen.
Der Board-PC löscht diese Lobby und bestätigt, dass sie nicht mehr existiert.
Nach zwei Sekunden öffnet die Accountzentrale die Autodarts-Startseite bei den
beiden betroffenen Accountspielern. Nach Bestätigung und weiteren drei Sekunden
erstellt das Script eine neue Lobby und lädt erneut ein. Lokale Gäste benötigen
keine Portal-Sitzung und werden in der neuen Lobby wieder angelegt.

Beide Container und das passende Board-Script auf Version 2.4.0 aktualisieren.
Die Accountzentrale einmal im selben Browser des Board-PCs anmelden:
Tampermonkey-Menü **Turnier-Board: Accountzentrale anmelden**. Der Zugriff läuft
über den vorhandenen Schutz der Website; es gibt kein zusätzliches Script-Passwort.
Für lokale Tests kann im Menü **Accountzentrale-Adresse** die Adresse
`http://192.168.178.137:18080` eingestellt werden.

Betroffene Accounts müssen in der Accountzentrale aktiv angemeldet sein und
Einladungen automatisch annehmen. Die Zuordnung erfolgt über beobachtete echte
Autodarts-Account-IDs, unabhängig vom Anzeigenamen der Portal-Sitzung. Login-Tokens
werden dafür nicht gespeichert oder zwischen den Anwendungen übertragen.
Fehlt die Zuordnung, die Spieler-Sitzung im Portal neu laden und anmelden.
Sitzungen in einem anderen laufenden Spiel oder einer anderen Lobby werden nicht
zurückgesetzt. Der Neustart pausiert dann mit einer konkreten Fehlermeldung.

Die Automatik muss aktiv sein; das Board-Script muss laufen. Unklare Lobby-Erstellung,
bereits gestartete Matches und gespeicherte Ergebnisse werden nicht mit diesem
Button zurückgesetzt. Wiederholte Anfragen derselben Neustart-ID setzen eine bereits
bestätigte Sitzung nicht erneut zurück, auch nach einem Portal-Container-Neustart.

Turnierplaner: https://turnier.mulich.de/ · Accounts und Downloads:
https://dartportal.mulich.de/

## Update

Beide Container auf die neue Version aktualisieren und auf jedem Board-PC das
passende Scheiben-Script **2.4.0** installieren bzw. aktualisieren:

- Blau: https://dartportal.mulich.de/static/turnier-blau.user.js
- Rot: https://dartportal.mulich.de/static/turnier-rot.user.js
- Schwarz: https://dartportal.mulich.de/static/turnier-schwarz.user.js

Nur das jeweilige Script aktivieren; das bisherige automatische Script deaktivieren.
Die Board-ID ist fest hinterlegt und wird nicht mehr aus dem Accountnamen ermittelt.
Der korrekte Board-Account muss weiterhin in Autodarts angemeldet sein. Das Script
beobachtet erneuerte Login-Tokens aus den Autodarts-Login-Antworten; Tokens werden
weder gespeichert noch an den Turnierplaner gesendet.

Vor dem Start werden Scheibe **und Steuerungsrechte** für beide Spieler geprüft.
Auch bei bereits passender Board-ID wird der Host gegebenenfalls erneut zugewiesen.
Der Referee wird ausdrücklich ausgeschaltet, damit manuelle Dartkorrekturen möglich
bleiben. Ohne bestätigte Steuerungsrechte wird kein Match gestartet. Bei bestehenden
Spielen die Steuerungsrechte in Autodarts prüfen; laufende Spiele werden nicht verändert.

Wenn der Live-Match-Abruf nach dem letzten Leg HTTP 404 meldet, prüft das Script
weiter die gespeicherte Statistik genau dieses Matches. Nur passende Teilnehmer
und die exakt erreichte Sieg-Legzahl erlauben die Übernahme; ein 404 allein ist
kein Endergebnis. Fehlende oder unvollständige Statistik wird erneut geprüft,
ohne ein Ersatzmatch anzulegen. Bereits übernommene Matches dürfen auch bei
zwischenzeitlich verschwundenem Live-Status die Scheibe freigeben.

Beim Spielstart versucht das Script echtes Browser-Vollbild. Blockiert der Browser
es wegen fehlender Nutzerinteraktion, auf **⛶** im Script-Fenster klicken oder **F11**
drücken. Seitenwechsel können Browser-Vollbild beenden; F11 bleibt dafür die einfachste
Option. Diese Einschränkung lässt sich durch ein Tampermonkey-Script nicht umgehen.

Jeweils im Compose-Verzeichnis:

```sh
docker compose pull
docker compose up -d
```

Die Datenvolumes beibehalten. Die Migration ergänzt die Spielerverwaltung und
bewahrt vorhandene Turniere, Ergebnisse und laufende Zuordnungen.

## Passwortschutz der Website

Zusätzliche Board-Schlüssel und die Abfrage von `TOURNAMENT_ADMIN_KEY` wurden auf
Wunsch entfernt. Die Compose-Datei benötigt diese Variable nicht mehr. Alte
Board-Schlüssel werden nicht mehr verwendet. Das Script übermittelt ausschließlich
seine feste Board-ID als `X-Board-ID`; diese ID ist kein Geheimnis und kein
Zugriffsschutz. Die gesamte Anwendung einschließlich `/api/bridge/` wird durch
**den vorhandenen Passwortschutz im Reverse Proxy** geschützt.

**Eine zuvor eingerichtete NPM-Ausnahme für `/api/bridge/` wieder entfernen.**
In Nginx Proxy Manager beim Proxy Host `turnier.mulich.de` den dafür angelegten
Location-Block aus Advanced bzw. die betreffende Custom Location löschen.
Die normale Access List beibehalten. Keine direkte öffentliche Freigabe des
Container-Ports einrichten.

Auf jedem Board-PC `https://turnier.mulich.de/` einmal **im selben Browser und
Browserprofil** öffnen und den normalen Website-Login durchführen. Das Script
sendet zum Planer Browser-Anmeldedaten mit, statt einen zusätzlichen Bearer-
Board-Schlüssel zu setzen. Bei HTTP 401 auf **Website anmelden** klicken und den
Website-Login erneuern. Je nach Browser/Erweiterung muss die Übernahme des
Proxy-Logins am jeweiligen PC geprüft werden. Website-Passwörter werden vom Script
nicht abgefragt, gespeichert oder an Autodarts geschickt.

## Spielerverwaltung

Im Planer **Spieler** öffnen. Anzeigenamen hinzufügen, ändern und aus der
Auswahlliste entfernen. Optional den exakten Autodarts-Accountnamen zuweisen.
Ein kleiner blauer Haken bedeutet **Account zugewiesen**, nicht extern verifiziert.
Pro Account ist nur ein Spielerprofil erlaubt. Ein leeres Accountfeld bedeutet
**lokaler Spieler**; es werden weder ein Account noch eine Einladung benötigt.

Namen aus vorhandenen Turnieren und die acht Standardspieler stehen zunächst ohne
Accountzuordnung bereit. Eine Zuordnung wird nicht aus einem ähnlich klingenden
Namen geraten. Beim Umbenennen bleiben historische Turniernamen erhalten; frühere
Namen sind intern mit demselben Profil verknüpft. Entfernen betrifft die
Auswahlliste, nicht vergangene Turniere oder bereits laufende Spiele.
Änderungen an Accounts werden für noch nicht verknüpfte Begegnungen verwendet;
ein bereits beanspruchter Board-Auftrag speichert seine Teilnehmerzuordnung fest.

## Board-PCs einrichten

1. Tampermonkey und das zur Scheibe passende Board-Script installieren.
2. Auf dem PC bei https://play.autodarts.com/ mit dem zugehörigen Board-Account
   anmelden und die Seite neu laden. Der Turnierplaner-Login muss im selben
   Browserprofil erfolgt sein. Es gibt keine zusätzliche Schlüsselkopplung.
3. Andere Scripts zur automatischen Lobby-Steuerung, insbesondere „Lokale Spieler“
   oder Team Lobby Mode, während der Turnier-Automatik deaktivieren.
4. Nur Teilnehmer mit Accountzuordnung müssen als bestätigte Freunde der
   verwendeten Board-Accounts hinterlegt sein. Diese Spieleraccounts im Portal
   anmelden und die automatische Einladungsannahme der freigegebenen
   Board-Accounts aktivieren. Lokale Gäste brauchen keinen Portal-Login.
5. Bestehende fremde Spiele auf den Scheiben beenden. Im Planer unter **Autodarts**
   den Status aktualisieren und im gewünschten Turnier **Autodarts starten** wählen.

| Scheibe | Feste Board-ID |
| --- | --- |
| Blau | faa2cd5f-5d19-4e68-9749-1b7b95c753d4 |
| Rot | ad381dc0-7e86-45a1-9fa8-61c8b18ec89b |
| Schwarz | 6e390006-cdba-4ac5-b0bb-0e03eb880af6 |

Das Script-Fenster startet eingeklappt als kleine Schaltfläche „Darts · Scheibe“.
Mit einem Klick auf die Überschrift ein- oder ausklappen. Der Zustand bleibt pro
Scheibe gespeichert; die Automatik läuft auch bei eingeklapptem Fenster weiter.

## Ablauf

Startpunkte, Best of/First to, Anzahl Legs, In/Out, Bull-Wertung und maximale Runden
im Turnier wählen. Bull-off bleibt aus. Spieler 1 im Plan wirft an. Best of 3
bedeutet 2 Legs zum Sieg. Bei älteren Turnieren die Spielregeln ausdrücklich
speichern; ihre früheren Regeln sind nicht überliefert.

Die private Lobby kann zwei Accountspieler, zwei lokale Gäste oder einen Spieler
von jeder Art enthalten. Accounts werden anhand der Freundesliste eindeutig
aufgelöst und eingeladen. Lokale Spieler werden mit ihrem Turniernamen und der
festen Board-ID hinzugefügt. Beide spielen an derselben Scheibe. Das Script prüft
Teilnehmer, Reihenfolge, Board und Spielregeln vor dem Start. Ein versehentlich
fehlender oder mehrdeutiger zugewiesener Account wird nicht als Gast ersetzt.

Nur ein Turnier kann automatisch laufen. Pro Scheibe nur einen Script-Tab verwenden.
Alle Spiele eines Durchgangs müssen beendet sein, bevor der nächste beginnt.
Ergebnisse werden aus der gespeicherten Match-Statistik beiden Teilnehmern
zugeordnet und gegen das eingestellte Leg-Ziel geprüft. Einzelne Leg-Enden oder
Restpunkte zählen nicht als Turnierergebnis. Der Planer aktualisiert sich während
der Automatik alle fünf Sekunden; manuelle Ergebnisfelder sind gesperrt.

## Pause und Fehlerbehebung

Pausieren hält die Bearbeitung an; das externe Match läuft weiter und kann nach
Fortsetzen übernommen werden. Auch Abbrechen/Löschen im Planer beendet kein
Autodarts-Match. Bei unklarer Erstellung/Spielstart wird kein zweites Spiel angelegt.
Automatik pausieren, bestehende Lobby oder Match in Autodarts prüfen und beenden;
danach unter **Autodarts → Zuordnung zurücksetzen** zurücksetzen und fortsetzen.
Nach einem Seitenwechsel kann die Übernahme der Steuerung bis zu 75 Sekunden dauern.

Die Autodarts-Schnittstelle ist keine garantierte öffentliche Automatisierungs-API.
Backend, Teilnehmerzuordnung, Account-/Gast-Mischungen und Script-Ablauf werden mit
isolierten Fixtures getestet. Ein echter Start, Gastspiel und Ergebnisimport müssen
an euren PCs geprüft werden. Autodarts-Zugriffstokens bleiben im Board-Browser.

## Entwicklung

```sh
python scripts/generate_board_scripts.py
python -m pytest -q
node --check dartabend/static/app.js
node --check dartabend/static/integration.js
node --check dartabend/static/players.js
```

Der Generator schreibt identische Scripts in `dartabend/static` und in das
benachbarte Accountportal unter `../app/static`. Beide Repositories und Images
nach Script-Änderungen aktualisieren.
