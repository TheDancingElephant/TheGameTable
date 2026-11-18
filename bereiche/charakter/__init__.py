"""Bereich Charakter: Werte, wirksame Werte mit Modi (Buffs), EP, Stufenaufstieg.

Öffentlich (für andere Bereiche und die Shell):
    laden, speichern, existiert, alle, loeschen, wirksam, von_token, sc_token, tp_uebernehmen, attr_mod,
    waffe_info, meter_pro_feld, char_setzen, charakter_speichern, charakter_loeschen, pfad_setzen
    ep_info, ep_befehl, ep_vergeben, stufe_von, HG_EP
    modus_befehl, modi_zeit, modi_liste, modus_ziel
    aufstieg_spieler, aufstieg_sl
    MODI (Modus-Regeln: Vorlagen, Wirkungen), AUF (Aufstiegsregeln)
Fachereignisse, die dieser Bereich auslöst: charakter_modi (cid, eff), token_groesse (token, groesse).
Reaktionen: runde_vorbei, zeit_vergeht → Modi laufen ab.
"""
from . import aufstieg as AUF
from . import modi as MODI
from .aufstieg_ablauf import sl as aufstieg_sl, spieler as aufstieg_spieler
from .ep import HG_EP, ep_befehl, ep_info, ep_vergeben, stufe_von, trefferwuerfel
from .modi_befehle import befehl as modus_befehl, liste as modi_liste, zeit as modi_zeit, ziel as modus_ziel
from .werte import (alle, attr_mod, char_setzen, charakter_loeschen, charakter_speichern, existiert, laden, loeschen,
                    meter_pro_feld, pfad_setzen, sc_token, speicherbar, speichern, tp_uebernehmen, von_token,
                    waffe_info, wirksam)

__all__ = ["AUF", "MODI", "HG_EP", "alle", "attr_mod", "aufstieg_sl", "aufstieg_spieler", "char_setzen",
           "charakter_loeschen", "charakter_speichern", "ep_befehl", "ep_info", "ep_vergeben", "existiert", "laden",
           "loeschen", "meter_pro_feld", "modi_liste", "modi_zeit", "modus_befehl", "modus_ziel", "pfad_setzen",
           "sc_token", "speicherbar", "speichern", "stufe_von", "tp_uebernehmen", "trefferwuerfel", "von_token",
           "waffe_info", "wirksam"]
