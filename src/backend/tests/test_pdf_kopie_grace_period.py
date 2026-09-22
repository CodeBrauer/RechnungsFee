"""
Regressionstest für Issue #394: Der allererste Druckvorgang einer Rechnung bekam beim
Speichern über den nativen PDF-Viewer im Tauri-Fenster fälschlich den KOPIE-Stempel.

Ursache: openInPdfWindow() (client.ts) navigiert das Fenster direkt auf die Backend-PDF-URL.
Klickt die Nutzerin dort auf den eigenen Speichern-Button des nativen Viewers, fragt der
Viewer dieselbe URL ein zweites Mal ab. Die erste Anfrage hat das Original dabei bereits
archiviert (rechnung.original_pdf_pfad gesetzt) - die zweite, technisch bedingte Anfrage traf
dadurch auf den "Kopie"-Zweig und bekam den Stempel, obwohl es nie ein echtes zweites Drucken
war. Fix: eine kurze Gnadenfrist nach dem Archivieren liefert weiterhin das unverändere
Original, keine echte Kopie.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.rechnungen import rechnung_als_pdf
from database.connection import Base
from database.models import Rechnung, Unternehmen


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Unternehmen(firmenname="Test GmbH", strasse="Teststr.", hausnummer="1", plz="12345", ort="Testort"))
    session.commit()
    yield session
    session.close()


def _rechnung(db) -> Rechnung:
    r = Rechnung(
        typ="ausgang", rechnungsnummer="RE-2026-42", datum=date(2026, 1, 5),
        dokument_typ="Rechnung", brutto_gesamt=Decimal("119.00"),
        netto_gesamt=Decimal("100.00"), ust_gesamt=Decimal("19.00"),
        ist_entwurf=False, zahlungsstatus="offen", bezahlt_betrag=Decimal("0.00"),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _hat_kopie_stempel(pdf_bytes: bytes) -> bool:
    import io
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "KOPIE" in reader.pages[0].extract_text()


def test_erster_druck_und_sofortiger_zweitabruf_beide_ohne_kopie_stempel(db):
    """Simuliert den nativen Viewer, der dieselbe URL kurz nach dem ersten Laden erneut
    abruft (Speichern-Button)."""
    r = _rechnung(db)

    erster = rechnung_als_pdf(r.id, db=db)
    assert not _hat_kopie_stempel(erster.body)

    zweiter = rechnung_als_pdf(r.id, db=db)
    assert not _hat_kopie_stempel(zweiter.body)


def test_echtes_zweites_drucken_nach_gnadenfrist_bekommt_kopie_stempel(db):
    """Regressionsschutz: die Gnadenfrist darf kein Dauer-Freifahrtschein werden - ein
    tatsächlich späterer, echter zweiter Druck muss weiterhin den KOPIE-Stempel bekommen."""
    r = _rechnung(db)

    erster = rechnung_als_pdf(r.id, db=db)
    assert not _hat_kopie_stempel(erster.body)

    r.ausgegeben_am = datetime.now() - timedelta(minutes=5)
    db.commit()

    spaeter = rechnung_als_pdf(r.id, db=db)
    assert _hat_kopie_stempel(spaeter.body)
