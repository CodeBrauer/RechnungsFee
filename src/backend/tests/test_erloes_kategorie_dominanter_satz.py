"""
Regressionstest für den Nebenfund aus Issue #389: _erloes_kategorie() ermittelt den
"dominanten" USt-Satz einer Rechnung mit gemischten Sätzen anhand des höchsten
Netto-ANTEILS - dafür wurde pos.netto (reiner Stückpreis, seit Migration 139) direkt
aufsummiert statt der tatsächlichen Positionssumme (Menge x Einzelpreis). Bei
unterschiedlichen Mengen kann das den falschen Satz als "dominant" auswählen und damit
die falsche Erlös-Kategorie/Kontonummer für die Zahlungsbuchung liefern.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.rechnungen import _erloes_kategorie
from database.connection import Base
from database.models import Kategorie, Rechnung, Rechnungsposition


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _kategorien(db):
    db.add(Kategorie(name="Betriebseinnahmen", kontenart="Erlös", konto_skr03="8400", konto_skr04="4400"))
    db.add(Kategorie(name="Betriebseinnahmen (7%)", kontenart="Erlös", konto_skr03="8300", konto_skr04="4300"))
    db.commit()


def test_dominanter_satz_beruecksichtigt_menge():
    """Position A: 1 x 100,00 EUR bei 19% (Positionssumme 100,00).
    Position B: 10 x 50,00 EUR bei 7% (Positionssumme 500,00).
    Der tatsächliche Netto-Anteil liegt klar bei 7% (500 vs. 100) - reine
    Stückpreis-Summierung (100 vs. 50) würde fälschlich 19% als dominant liefern."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    _kategorien(db)

    rechnung = Rechnung(
        typ="ausgang", rechnungsnummer="RE-1", datum=date(2026, 1, 1),
        brutto_gesamt=Decimal("689.00"), netto_gesamt=Decimal("600.00"), ist_entwurf=False,
    )
    db.add(rechnung)
    db.flush()
    db.add(Rechnungsposition(
        rechnung_id=rechnung.id, position_nr=1, beschreibung="Beratung",
        menge=Decimal("1"), netto=Decimal("100.00"), ust_satz=Decimal("19"),
        ust_betrag=Decimal("19.00"), brutto=Decimal("119.00"),
    ))
    db.add(Rechnungsposition(
        rechnung_id=rechnung.id, position_nr=2, beschreibung="Ware",
        menge=Decimal("10"), netto=Decimal("50.00"), ust_satz=Decimal("7"),
        ust_betrag=Decimal("35.00"), brutto=Decimal("535.00"),
    ))
    db.commit()
    db.refresh(rechnung)

    kat_id, kat = _erloes_kategorie(db, rechnung)

    assert kat.name == "Betriebseinnahmen (7%)"
