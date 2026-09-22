"""
Regressionstest für Issue #400-Folgefund (§19 UStG bei Buchungsvorlagen).

buche_vorlage() baut den Journal-Eintrag direkt, ohne über journal.py::_felder_aus_data() zu
laufen (das die §19-Sperre schon kennt, Issue #397) - v.ust_satz und der daraus abgeleitete
Vorsteuerabzug wurden bislang unabhängig vom Kleinunternehmerstatus übernommen. Bei einer
Ausgabe (z.B. Miete über eine Wiederkehrende Buchung) hätte ein Kleinunternehmer dadurch jeden
Monat einen unzulässigen echten Vorsteuerabzug gutgeschrieben bekommen; bei einer Einnahme
hätte fälschlich USt auf den eigenen Umsatz ausgewiesen werden können.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.buchungsvorlagen import BuchenRequest, buche_vorlage
from database.connection import Base
from database.models import Buchungsvorlage, Journaleintrag, Unternehmen


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _kleinunternehmer(db) -> None:
    db.add(Unternehmen(
        firmenname="Test GmbH", strasse="Teststr.", hausnummer="1", plz="12345", ort="Testort",
        ist_kleinunternehmer=True,
    ))
    db.commit()


def _vorlage(db, art: str, ust_satz: str = "19", betrag: str = "119.00", ist_brutto: bool = True) -> Buchungsvorlage:
    v = Buchungsvorlage(
        bezeichnung="Büromiete" if art == "Ausgabe" else "Abo-Erlös",
        betrag=Decimal(betrag), ist_brutto=ist_brutto, ust_satz=Decimal(ust_satz),
        intervall="monatlich", naechstes_datum=date(2026, 1, 1), modus="direkt", art=art,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_ausgabe_kleinunternehmer_behaelt_realen_ust_satz_aber_keinen_vorsteuerabzug(db):
    """Miete über eine Wiederkehrende Buchung: der reale USt-Satz des Vermieters bleibt
    erhalten (119 € brutto -> 100 € netto + 19 € USt), aber es darf keine Vorsteuer
    gutgeschrieben werden."""
    _kleinunternehmer(db)
    v = _vorlage(db, "Ausgabe", ust_satz="19", betrag="119.00", ist_brutto=True)

    buche_vorlage(v.id, data=BuchenRequest(), db=db)

    eintrag = db.query(Journaleintrag).filter(Journaleintrag.buchungsvorlage_id == v.id).first()
    assert eintrag.brutto_betrag == Decimal("119.00")
    assert eintrag.ust_satz == Decimal("19")
    assert eintrag.ust_betrag == Decimal("19.00")
    assert eintrag.vorsteuerabzug is False
    assert eintrag.vorsteuer_betrag == Decimal("0.00")


def test_einnahme_kleinunternehmer_zeigt_keine_ust(db):
    """Ein Kleinunternehmer darf auf eigene Einnahmen nie USt ausweisen, auch wenn die
    Vorlage (versehentlich) mit einem USt-Satz > 0 angelegt wurde."""
    _kleinunternehmer(db)
    v = _vorlage(db, "Einnahme", ust_satz="19", betrag="119.00", ist_brutto=True)

    buche_vorlage(v.id, data=BuchenRequest(), db=db)

    eintrag = db.query(Journaleintrag).filter(Journaleintrag.buchungsvorlage_id == v.id).first()
    assert eintrag.brutto_betrag == Decimal("119.00")
    assert eintrag.netto_betrag == Decimal("119.00")
    assert eintrag.ust_satz == Decimal("0")
    assert eintrag.ust_betrag == Decimal("0.00")


def test_ausgabe_ohne_kleinunternehmer_bleibt_unveraendert(db):
    """Regressionsschutz: ohne Kleinunternehmerstatus muss der Vorsteuerabzug wie bisher
    automatisch anhand des USt-Satzes gewährt werden."""
    v = _vorlage(db, "Ausgabe", ust_satz="19", betrag="119.00", ist_brutto=True)

    buche_vorlage(v.id, data=BuchenRequest(), db=db)

    eintrag = db.query(Journaleintrag).filter(Journaleintrag.buchungsvorlage_id == v.id).first()
    assert eintrag.ust_satz == Decimal("19")
    assert eintrag.vorsteuerabzug is True
    assert eintrag.vorsteuer_betrag == Decimal("19.00")
