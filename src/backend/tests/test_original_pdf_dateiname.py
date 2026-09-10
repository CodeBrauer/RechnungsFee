"""
Regressionstest für Issue #390: Das archivierte Original-PDF hieß bisher pauschal
<interne-DB-ID>.pdf, ohne jeden Bezug zur Rechnungsnummer und ohne Unterscheidung
zwischen Eingang und Ausgang. Jetzt: <Rechnungsnummer>_<interne-ID>.pdf - die ID bleibt
als Suffix Pflicht, weil rechnungsnummer bei Eingangsrechnungen (Lieferanten-Rechnungsnr.)
manuell erfasst und nicht datenbankweit eindeutig ist.
"""
from types import SimpleNamespace

from utils.pdf_kopie import speichere_original_pdf


def _rechnung(id_, rechnungsnummer):
    return SimpleNamespace(id=id_, rechnungsnummer=rechnungsnummer)


def test_dateiname_nutzt_rechnungsnummer_und_id(tmp_path):
    rel_pfad = speichere_original_pdf(tmp_path, _rechnung(42, "RE-260103"), b"%PDF-fake-ausgang")

    assert rel_pfad == "uploads/rechnungen/RE-260103_42.pdf"
    assert (tmp_path / "uploads" / "rechnungen" / "RE-260103_42.pdf").read_bytes() == b"%PDF-fake-ausgang"


def test_dateiname_unterscheidet_eingang_und_ausgang_praefix(tmp_path):
    rel_pfad = speichere_original_pdf(tmp_path, _rechnung(7, "ER-260001"), b"%PDF-fake-eingang")

    assert rel_pfad == "uploads/rechnungen/ER-260001_7.pdf"


def test_gleiche_rechnungsnummer_verschiedener_lieferanten_ueberschreibt_sich_nicht(tmp_path):
    """Eingangsrechnungsnummern sind manuell erfasst und nicht eindeutig - zwei Belege
    unterschiedlicher Lieferanten mit zufällig identischer Nummer dürfen sich beim
    Archivieren nicht gegenseitig überschreiben (die interne ID im Dateinamen verhindert das)."""
    pfad_a = speichere_original_pdf(tmp_path, _rechnung(10, "12345"), b"Lieferant A")
    pfad_b = speichere_original_pdf(tmp_path, _rechnung(11, "12345"), b"Lieferant B")

    assert pfad_a != pfad_b
    assert (tmp_path / pfad_a).read_bytes() == b"Lieferant A"
    assert (tmp_path / pfad_b).read_bytes() == b"Lieferant B"


def test_slash_und_leerzeichen_in_rechnungsnummer_werden_ersetzt(tmp_path):
    """Manuell erfasste Rechnungsnummern können Zeichen enthalten, die auf Dateisystemebene
    problematisch sind (z.B. '/' als Pfadtrenner unter Linux/macOS)."""
    rel_pfad = speichere_original_pdf(tmp_path, _rechnung(3, "2026/07 Beleg 1"), b"x")

    assert rel_pfad == "uploads/rechnungen/2026-07_Beleg_1_3.pdf"


def test_fehlende_rechnungsnummer_faellt_auf_id_zurueck(tmp_path):
    rel_pfad = speichere_original_pdf(tmp_path, _rechnung(99, None), b"x")

    assert rel_pfad == "uploads/rechnungen/99_99.pdf"
