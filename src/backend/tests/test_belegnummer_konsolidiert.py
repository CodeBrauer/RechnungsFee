"""
Regressionstest für Issue #399: die drei bisherigen, leicht unterschiedlich fähigen Kopien von
_belegnr_aus_format() (journal.py, rechnungen.py, wiederkehrend.py) wurden zu einer gemeinsamen
Funktion in utils/belegnummer.py zusammengeführt. Dieser Test deckt beide zuvor nur in je einer
der Kopien vorhandenen Fähigkeiten gemeinsam ab:
  - Gross-/Kleinschreibung der Platzhalter wird nicht unterschieden (war nur in journal.py)
  - deutsche Aliase JJJJ/JJ/NN neben YYYY/YY/# (waren nur in rechnungen.py)
wiederkehrend.py's eigene Kopie kannte weder das eine noch das andere und wird hier ebenfalls
mit abgedeckt, da sie exakt dieselbe Funktion jetzt importiert statt selbst zu rechnen.
"""
from datetime import date

from utils.belegnummer import belegnr_aus_format


def test_kleinbuchstaben_platzhalter():
    assert belegnr_aus_format("da-tt.mm.yyyy-####", date(2026, 8, 28), 7) == "da-28.08.2026-0007"


def test_deutsche_aliase_jjjj_jj():
    assert belegnr_aus_format("DA-JJJJ-####", date(2026, 8, 28), 3) == "DA-2026-0003"
    assert belegnr_aus_format("DA-JJ-####", date(2026, 8, 28), 3) == "DA-26-0003"


def test_nn_alias_fuer_laufende_nummer():
    assert belegnr_aus_format("DA-YYNN", date(2026, 8, 28), 3) == "DA-2603"


def test_einzelnes_n_in_praefix_wird_nicht_versehentlich_ersetzt():
    """Nur NN (mind. 2x) ist der Nummern-Alias - ein einzelnes N in einem Präfix wie "DAN-"
    darf nicht als Nummernplatzhalter missverstanden werden."""
    assert belegnr_aus_format("DAN-YY-####", date(2026, 8, 28), 3) == "DAN-26-0003"


def test_yyyy_geht_vor_yy_auch_in_kombination_mit_jjjj():
    assert belegnr_aus_format("YYYY/JJJJ", date(2026, 1, 1), 1) == "2026/2026"


def test_konsolidierte_funktion_wird_aus_allen_drei_modulen_reexportiert():
    """journal.py/rechnungen.py importieren die gemeinsame Funktion jetzt nur noch, statt sie
    selbst zu definieren - stellt sicher, dass der Re-Export nicht versehentlich wegfällt."""
    from api.journal import _belegnr_aus_format as aus_journal
    from api.rechnungen import _belegnr_aus_format as aus_rechnungen

    assert aus_journal is belegnr_aus_format
    assert aus_rechnungen is belegnr_aus_format
