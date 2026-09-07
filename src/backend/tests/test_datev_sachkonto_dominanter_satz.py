"""
Regressionstest für den Nebenfund aus Issue #389: _sachkonto() (DATEV-Export) hat für
den Fallback-Weg über die Rechnungspositionen denselben Fehler wie _erloes_kategorie()
in api/rechnungen.py - der "dominante" USt-Satz wurde über die Summe der reinen
Stückpreise (pos.netto) statt der tatsächlichen Positionssummen (Menge x Einzelpreis)
ermittelt.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.datev import _sachkonto
from database.connection import Base
from database.models import Journaleintrag, Kategorie, Rechnung, Rechnungsposition


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_sachkonto_fallback_beruecksichtigt_menge(db):
    """Position A: 1 x 100,00 EUR bei 19% (Positionssumme 100,00).
    Position B: 10 x 50,00 EUR bei 7% (Positionssumme 500,00).
    Der tatsächliche Netto-Anteil liegt klar bei 7% - reine Stückpreis-Summierung
    (100 vs. 50) würde fälschlich 19% als dominant liefern und Konto 8400/4400 statt
    8300/4300 zurückgeben."""
    db.add(Kategorie(name="Betriebseinnahmen", kontenart="Erlös", konto_skr03="8400", konto_skr04="4400"))
    db.add(Kategorie(name="Betriebseinnahmen (7%)", kontenart="Erlös", konto_skr03="8300", konto_skr04="4300"))

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

    j = Journaleintrag(
        datum=date(2026, 1, 5), belegnr="RE-1", art="Einnahme", zahlungsart="Bank",
        netto_betrag=Decimal("600.00"), ust_betrag=Decimal("89.00"), brutto_betrag=Decimal("689.00"),
        beschreibung="RE-1", rechnung_id=rechnung.id,
    )
    db.add(j)
    db.commit()
    db.refresh(j)

    konto = _sachkonto(j, "SKR03", db)

    assert konto == "8300"
