"""
Regressionstests für Issue #385 (einfachere Alternative zur vollen Signaturverkettung):
ID-Lücken-Prüfung im GoBD-Export.

Journaleintrag/Tagesabschluss verwenden ein plattes INTEGER PRIMARY KEY (SQLite-rowid,
kein AUTOINCREMENT) - eine Lücke in der ID-Folge kann unter normalem App-Betrieb nicht
entstehen (kein Code-Pfad löscht jemals eine dieser Zeilen), beweist also eine Löschung
außerhalb der Anwendung.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from database.connection import Base
from database.models import Journaleintrag, Tagesabschluss
from utils.gobd_export import _finde_id_luecken, export_integritaet_csv


def test_finde_id_luecken_leere_liste():
    assert _finde_id_luecken([]) == []


def test_finde_id_luecken_keine_luecke():
    assert _finde_id_luecken([1, 2, 3, 4]) == []


def test_finde_id_luecken_eine_luecke():
    assert _finde_id_luecken([1, 2, 4, 5]) == [3]


def test_finde_id_luecken_mehrere_luecken_unsortierte_eingabe():
    assert _finde_id_luecken([5, 1, 8, 2]) == [3, 4, 6, 7]


def test_finde_id_luecken_einzelnes_element():
    assert _finde_id_luecken([42]) == []


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _eintrag(db, **kwargs) -> Journaleintrag:
    defaults = dict(
        datum=date(2026, 1, 10), belegnr="J-1", beschreibung="Testbuchung",
        zahlungsart="Bank", art="Ausgabe",
        netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
        brutto_betrag=Decimal("119.00"), vorsteuerabzug=True, immutable=True,
    )
    defaults.update(kwargs)
    e = Journaleintrag(**defaults)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def test_export_findet_keine_luecke_bei_lueckenloser_folge(db):
    for i in range(3):
        _eintrag(db, belegnr=f"J-{i}")

    _, stats = export_integritaet_csv(db, 2026)

    assert stats["journal_id_luecken"] == []


def test_export_findet_luecke_nach_aussenstehender_loeschung(db):
    _eintrag(db, belegnr="J-1")
    e2 = _eintrag(db, belegnr="J-2")
    e2_id = e2.id
    _eintrag(db, belegnr="J-3")

    # Simuliert eine Löschung außerhalb der Anwendung (z.B. direkter DB-Zugriff bei
    # gestoppter App, ohne die Schutz-Trigger - hier absichtlich ohne
    # _setup_gobd_triggers() aufgebaut, um exakt dieses Szenario nachzustellen).
    db.execute(text("DELETE FROM journal WHERE id = :id"), {"id": e2_id})
    db.commit()
    db.expire_all()

    _, stats = export_integritaet_csv(db, 2026)

    assert stats["journal_id_luecken"] == [e2_id]


def test_export_findet_luecke_bei_tagesabschluss(db):
    """Löscht bewusst die MITTLERE von drei Zeilen - eine innere Lücke, die die
    min/max-basierte Prüfung erkennen kann (siehe Docstring von _finde_id_luecken zur
    bekannten Einschränkung bei Rand-Löschungen: ältester/neuester Datensatz)."""
    abschluesse = [
        Tagesabschluss(
            datum=date(2026, 1, i), uhrzeit="18:00:00",
            anfangsbestand=Decimal("0"), soll_endbestand=Decimal("0"), ist_endbestand=Decimal("0"),
            immutable=True,
        )
        for i in (1, 2, 3)
    ]
    db.add_all(abschluesse)
    db.commit()
    mittlere_id = abschluesse[1].id

    db.execute(text("DELETE FROM tagesabschluesse WHERE id = :id"), {"id": mittlere_id})
    db.commit()
    db.expire_all()

    _, stats = export_integritaet_csv(db, 2026)

    assert stats["tagesabschluss_id_luecken"] == [mittlere_id]
