"""Bereich Magie: Zauberplätze, Zauberpools (z. B. Barde), spontanes Zaubern, Domänen, Vorbereiten, Zauberbuch,
Zauber wirken, Klassenfähigkeiten, Rast.

Öffentlich: zauber_def, frei, platz_verbrauchen, wirken, wirken_spieler, faehigkeit_nutzen, faehigkeit_spieler,
rast, vorbereiten, zauberbuch, ansicht (berechnete Werte für die Oberfläche), zauberklasse, kann_vorbereiten.
Fachereignisse, die dieser Bereich auslöst: zeit_vergeht (Rast, 4800 Runden).
"""
from .faehigkeiten import nutzen as faehigkeit_nutzen, nutzen_spieler as faehigkeit_spieler
from .vorbereiten import kann_vorbereiten, neu_vorbereiten, plaetze, zauberklasse
from .zauber import (ansicht, beruehrungsbonus, formel, frei, platz_verbrauchen, rast, reichweite_m, vorbereiten,
                     wirken, wirken_spieler, zauber_def, zauberbuch, zauberstufe)

__all__ = ["ansicht", "beruehrungsbonus", "faehigkeit_nutzen", "faehigkeit_spieler", "formel", "frei",
           "kann_vorbereiten", "neu_vorbereiten", "plaetze", "platz_verbrauchen", "rast", "reichweite_m",
           "vorbereiten", "wirken", "wirken_spieler", "zauber_def", "zauberbuch", "zauberklasse", "zauberstufe"]
