"""
Gemeinsame Belegnummer-Formatierung für alle Nummernkreise (Rechnungen, Journal, Angebote,
Lieferscheine, wiederkehrende Rechnungen etc.).

Vorher gab es drei fast identische, aber leicht unterschiedlich fähige Kopien dieser Funktion
(journal.py, rechnungen.py, wiederkehrend.py) - konsolidiert im Zuge von Issue #399, das
zusätzlich einen fest hinterlegten "RE-"/"ER-"-Präfix vor dem eigentlich frei konfigurierbaren
Format aufdeckte. Diese Version vereint beide bisherigen Fähigkeiten:
  - Gross-/Kleinschreibung der Platzhalter wird nicht unterschieden (aus journal.py)
  - deutsche Aliase JJJJ/JJ/NN neben YYYY/YY/# (aus rechnungen.py)
"""

import re as _re
from datetime import date


def belegnr_aus_format(format_str: str, datum: date, nr: int) -> str:
    """Wendet das Format-Template an. YYYY/JJJJ=Jahr 4-stellig, YY/JJ=Jahr 2-stellig,
    MM=Monat, TT=Tag, #=Nummernstelle (Anzahl # bestimmt die Nullauffüllung), NN(+)=Alias für #
    (mind. 2 N, damit ein einzelner Buchstabe in einem Präfix nicht versehentlich ersetzt wird).
    Gross-/Kleinschreibung wird nicht unterschieden (ein von Hand eingetipptes "re-tt.mm.yyyy"
    wird genauso erkannt wie "RE-TT.MM.YYYY"). Reihenfolge YYYY vor YY (bzw. JJJJ vor JJ) bleibt
    wichtig, sonst würde YYYY fälschlich als zwei YY erkannt."""
    year_4 = str(datum.year)
    year_2 = year_4[-2:]
    month  = f"{datum.month:02d}"
    day    = f"{datum.day:02d}"

    result = _re.sub("YYYY", year_4, format_str, flags=_re.IGNORECASE)
    result = _re.sub("JJJJ", year_4, result,     flags=_re.IGNORECASE)
    result = _re.sub("YY",   year_2, result,     flags=_re.IGNORECASE)
    result = _re.sub("JJ",   year_2, result,     flags=_re.IGNORECASE)
    result = _re.sub("MM",   month,  result,     flags=_re.IGNORECASE)
    result = _re.sub("TT",   day,    result,     flags=_re.IGNORECASE)

    def _pad(m: _re.Match) -> str:
        return str(nr).zfill(len(m.group()))

    result = _re.sub(r"#+",  _pad, result)
    result = _re.sub(r"NN+", _pad, result, flags=_re.IGNORECASE)
    return result
