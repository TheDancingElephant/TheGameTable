"""Fachbereiche des Spieltischs (modularer Monolith), siehe ARCHITEKTUR.md.

Jeder Bereich ist ein Unterpaket mit öffentlichen Funktionen in seinem __init__.py. `REAKTIONEN` verdrahtet
Fachereignisse mit den Bereichen, die darauf reagieren (wird von der Shell in jeden Kontext gegeben).
"""

REAKTIONEN = {}


def reaktion(ereignis):
    """Dekorator: Funktion(kx, **daten) als Reaktion auf ein Fachereignis eintragen."""
    def deko(f):
        REAKTIONEN.setdefault(ereignis, []).append(f)
        return f
    return deko
