"""
Regressionstest für Issue #399, Wunsch 2: eigener, optionaler Nummernkreis für aus
Wiederkehrenden Vorlagen erzeugte Ausgangsrechnungen, damit sie nicht zwangsläufig die
laufende Nummernfolge der normalen Ausgangsrechnungen mit hochzählen.

Default: gemeinsamer Kreis (rechnung_ausgang) wie bisher. Erst wenn der eigene Kreis
(rechnung_wiederkehrend) aktiv geschaltet ist, wird er genutzt. Einweg-Sperre: ist er einmal
aktiv UND hat mindestens eine Nummer vergeben, lässt er sich nicht mehr zurückschalten - sonst
könnten später doppelte Rechnungsnummern entstehen, wenn beide Kreise denselben Stand erreichen.
"""
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.wiederkehrend import _naechste_rechnungsnr
from api.nummernkreise import update_nummernkreis
from api.schemas import NummernkreisUpdate
from database.connection import Base
from database.models import Nummernkreis


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Nummernkreis(bezeichnung="Ausgangsrechnungen", typ="rechnung_ausgang", format="RE-YY####", naechste_nr=1, reset_jaehrlich=True))
    session.add(Nummernkreis(bezeichnung="Wiederkehrende Rechnungen", typ="rechnung_wiederkehrend", format="DA-YY####", naechste_nr=1, reset_jaehrlich=True, aktiv=False))
    session.commit()
    yield session
    session.close()


def test_standardmaessig_wird_der_gemeinsame_kreis_genutzt(db):
    nr = _naechste_rechnungsnr(date(2026, 1, 15), db)
    assert nr == "RE-260001"

    ausgang = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_ausgang").first()
    wiederkehrend = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    assert ausgang.naechste_nr == 2  # gemeinsamer Kreis wurde hochgezaehlt
    assert wiederkehrend.naechste_nr == 1  # eigener Kreis unangetastet, da inaktiv


def test_aktivierter_eigener_kreis_wird_genutzt_und_stoert_normale_folge_nicht(db):
    wiederkehrend = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    wiederkehrend.aktiv = True
    db.commit()

    nr1 = _naechste_rechnungsnr(date(2026, 1, 15), db)
    nr2 = _naechste_rechnungsnr(date(2026, 2, 15), db)

    assert nr1 == "DA-260001"
    assert nr2 == "DA-260002"

    ausgang = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_ausgang").first()
    assert ausgang.naechste_nr == 1  # normale Rechnungsfolge komplett unberuehrt


def test_deaktivieren_vor_erster_nutzung_bleibt_erlaubt(db):
    wiederkehrend = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    wiederkehrend.aktiv = True
    db.commit()

    ergebnis = update_nummernkreis(wiederkehrend.id, NummernkreisUpdate(aktiv=False), db)

    assert ergebnis.aktiv is False


def test_deaktivieren_nach_erster_nutzung_wird_verweigert(db):
    wiederkehrend = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    wiederkehrend.aktiv = True
    db.commit()

    _naechste_rechnungsnr(date(2026, 1, 15), db)  # verbraucht die erste Nummer -> naechste_nr wird 2

    with pytest.raises(HTTPException) as exc_info:
        update_nummernkreis(wiederkehrend.id, NummernkreisUpdate(aktiv=False), db)

    assert exc_info.value.status_code == 409

    # Zustand bleibt unveraendert aktiv.
    unveraendert = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    assert unveraendert.aktiv is True


def test_andere_felder_bleiben_trotz_sperre_editierbar(db):
    """Die Sperre betrifft ausschliesslich das Deaktivieren - das Format darf weiterhin
    angepasst werden, auch nachdem der Kreis schon genutzt wurde."""
    wiederkehrend = db.query(Nummernkreis).filter(Nummernkreis.typ == "rechnung_wiederkehrend").first()
    wiederkehrend.aktiv = True
    db.commit()
    _naechste_rechnungsnr(date(2026, 1, 15), db)

    ergebnis = update_nummernkreis(wiederkehrend.id, NummernkreisUpdate(format="ABO-YY####"), db)

    assert ergebnis.format == "ABO-YY####"
    assert ergebnis.aktiv is True
