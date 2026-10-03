"""Spielplanregeln aus dem ursprünglichen Turnierskript."""
import random


def round_robin_runden(spieler):
    """
    Erstellt Jeder-gegen-jeden-Runden.
    Pro Runde spielt jeder Spieler höchstens einmal.
    Bei ungerader Spieleranzahl hat pro Runde ein Spieler Pause.
    """
    spieler_liste = spieler.copy()
    random.shuffle(spieler_liste)

    if len(spieler_liste) % 2 == 1:
        spieler_liste.append("PAUSE")

    anzahl = len(spieler_liste)
    runden = []

    for _ in range(anzahl - 1):
        paarungen = []

        for i in range(anzahl // 2):
            spieler1 = spieler_liste[i]
            spieler2 = spieler_liste[anzahl - 1 - i]

            if spieler1 != "PAUSE" and spieler2 != "PAUSE":
                paarungen.append((spieler1, spieler2))

        runden.append(paarungen)

        # Rotation: erster Spieler bleibt fest, alle anderen rotieren
        spieler_liste = [spieler_liste[0]] + [spieler_liste[-1]] + spieler_liste[1:-1]

    return runden


def beste_scheibe_waehlen(spieler1, spieler2, freie_scheiben, scheiben_zaehler, letzte_scheibe):
    """
    Wählt aus den freien Scheiben die beste Scheibe aus.
    Ziel:
    - Spieler sollen möglichst gleichmäßig auf allen Scheiben spielen.
    - Spieler sollen möglichst nicht direkt wieder auf derselben Scheibe spielen.
    """
    beste_scheibe = None
    beste_wertung = None

    for scheibe in freie_scheiben:
        wertung = 0

        # Je öfter beide Spieler schon auf dieser Scheibe gespielt haben,
        # desto schlechter wird diese Scheibe bewertet.
        wertung += scheiben_zaehler[spieler1].get(scheibe, 0)
        wertung += scheiben_zaehler[spieler2].get(scheibe, 0)

        # Strafe, wenn ein Spieler direkt wieder auf derselben Scheibe spielen würde.
        if letzte_scheibe.get(spieler1) == scheibe:
            wertung += 3

        if letzte_scheibe.get(spieler2) == scheibe:
            wertung += 3

        if beste_wertung is None or wertung < beste_wertung:
            beste_wertung = wertung
            beste_scheibe = scheibe

    return beste_scheibe


def startspieler_waehlen(spieler1, spieler2, start_zaehler, letzter_startspieler):
    """
    Wählt den Startspieler möglichst fair.
    Ziel:
    - Nicht immer derselbe Spieler soll anfangen.
    - Die Anzahl der Anwürfe soll ungefähr gleichmäßig verteilt sein.
    """
    wertung1 = start_zaehler[spieler1]
    wertung2 = start_zaehler[spieler2]

    # Kleine Strafe, wenn der Spieler in seinem letzten Spiel bereits angefangen hat.
    if letzter_startspieler.get(spieler1):
        wertung1 += 2

    if letzter_startspieler.get(spieler2):
        wertung2 += 2

    if wertung1 < wertung2:
        return spieler1, spieler2

    if wertung2 < wertung1:
        return spieler2, spieler1

    # Wenn beide gleich bewertet sind, entscheidet der Zufall.
    if random.choice([True, False]):
        return spieler1, spieler2

    return spieler2, spieler1


def spielplan_erstellen(spieler, scheiben):
    runden = round_robin_runden(spieler)

    scheiben_zaehler = {
        name: {scheibe: 0 for scheibe in scheiben}
        for name in spieler
    }

    start_zaehler = {
        name: 0 for name in spieler
    }

    letzte_scheibe = {}

    letzter_startspieler = {
        name: False for name in spieler
    }

    spielplan = []
    spielnummer = 1
    durchgang = 1

    for runden_nr, paarungen in enumerate(runden, start=1):
        random.shuffle(paarungen)

        belegte_scheiben_im_durchgang = []

        for spieler1, spieler2 in paarungen:

            # Wenn alle Scheiben in diesem Durchgang belegt sind,
            # beginnt ein neuer Durchgang.
            if len(belegte_scheiben_im_durchgang) >= len(scheiben):
                durchgang += 1
                belegte_scheiben_im_durchgang = []

            # Nur Scheiben verwenden, die im aktuellen Durchgang noch frei sind.
            freie_scheiben = [
                scheibe for scheibe in scheiben
                if scheibe not in belegte_scheiben_im_durchgang
            ]

            scheibe = beste_scheibe_waehlen(
                spieler1,
                spieler2,
                freie_scheiben,
                scheiben_zaehler,
                letzte_scheibe
            )

            belegte_scheiben_im_durchgang.append(scheibe)

            starter, zweiter = startspieler_waehlen(
                spieler1,
                spieler2,
                start_zaehler,
                letzter_startspieler
            )

            spielplan.append({
                "nr": spielnummer,
                "runde": runden_nr,
                "durchgang": durchgang,
                "scheibe": scheibe,
                "spieler1": starter,
                "spieler2": zweiter,
                "anwurf": starter
            })

            # Statistik aktualisieren
            scheiben_zaehler[spieler1][scheibe] += 1
            scheiben_zaehler[spieler2][scheibe] += 1

            letzte_scheibe[spieler1] = scheibe
            letzte_scheibe[spieler2] = scheibe

            # Merken, wer zuletzt angeworfen hat
            letzter_startspieler[spieler1] = False
            letzter_startspieler[spieler2] = False
            letzter_startspieler[starter] = True

            start_zaehler[starter] += 1
            spielnummer += 1

        # Nach jeder Runde beginnt der nächste freie Durchgang.
        # Beispiel bei 6 Spielern und 2 Scheiben:
        # Runde 1 braucht Durchgang 1 und 2.
        # Runde 2 beginnt dann mit Durchgang 3.
        if belegte_scheiben_im_durchgang:
            durchgang += 1

    return spielplan, scheiben_zaehler, start_zaehler
