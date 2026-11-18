// Gemeinsamer Zustand der Oberfläche (G) und Ansicht der Karte.
// ------------------------------------------------------------------ Zustand


export const G = {
  stand: null,
  charaktere: [],
  letzteLogId: 0,
  ersteLadung: true,
  rasterAn: true,
  barrierenAn: false,  // nur SL: erkannte Barrieren einzeichnen
  barrierenCache: { schluessel: "", daten: null, laedt: false },
  werkzeug: "bewegen",
  ausgewaehlt: null,  // Token-ID
  ziehen: null,  // laufende Maus-Aktion
  platzieren: null,  // charId, die auf die Karte gesetzt wird
  pings: [],  // {x, y, t}
  hoverZelle: null,
  bildSchluessel: "",
  zielModus: null,  // {token, index, e}: Zauber/Fähigkeit wartet auf ein Ziel
};

export const ansicht = { zoom: 1, x: 0, y: 0, karteId: null };

export const bild = new Image();
