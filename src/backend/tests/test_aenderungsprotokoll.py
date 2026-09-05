"""
Regressionstests für Issue #385: Änderungsprotokoll.

1. Der Issue-#132-Reparaturblock in _migrate_signaturen() (kategorielose Einnahme-Buchungen
   aus Ausgangsrechnungen) protokolliert ab jetzt jede geänderte Zeile.
2. export_aenderungsprotokoll_csv() liefert die Einträge korrekt als CSV.
3. protokolliere_aenderung() funktioniert sowohl mit einer rohen Connection als auch mit
   einer ORM-Session.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import main
from database.connection import Base
from database.models import AenderungsProtokoll, Journaleintrag, Kategorie, Rechnung
from utils.aenderungsprotokoll import protokolliere_aenderung
from utils.gobd_export import export_aenderungsprotokoll_csv


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_kategorie_132_reparatur_wird_protokolliert(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)
    Session = sessionmaker(bind=eng)
    monkeypatch.setattr(main, "SessionLocal", Session)

    Base.metadata.create_all(bind=eng)
    db = Session()

    kat19 = Kategorie(name="Betriebseinnahmen", kontenart="Erlös", vorsteuer_prozent=0, ust_satz_standard=19)
    db.add(kat19)
    db.commit()
    db.refresh(kat19)

    rechnung = Rechnung(
        typ="ausgang", datum=date(2026, 1, 1),
        brutto_gesamt=Decimal("119.00"), netto_gesamt=Decimal("100.00"), ist_entwurf=False,
    )
    db.add(rechnung)
    db.flush()

    e = Journaleintrag(
        datum=date(2026, 1, 1), belegnr="J-1", beschreibung="Alte kategorielose Buchung",
        zahlungsart="Bank", art="Einnahme",
        netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
        brutto_betrag=Decimal("119.00"), vorsteuerabzug=False, immutable=True,
        rechnung_id=rechnung.id, kategorie_id=None,
    )
    db.add(e)
    db.commit()
    e_id = e.id
    kat19_id = kat19.id
    db.close()

    main._migrate_signaturen()

    db2 = Session()
    protokoll = db2.query(AenderungsProtokoll).filter(
        AenderungsProtokoll.tabelle == "journal", AenderungsProtokoll.datensatz_id == e_id,
    ).all()
    assert len(protokoll) == 1
    assert protokoll[0].feld == "kategorie_id"
    assert protokoll[0].alter_wert is None
    assert protokoll[0].neuer_wert == str(kat19_id)
    assert protokoll[0].migration_version == main.SCHEMA_VERSION
    assert "#132" in protokoll[0].grund
    db2.close()


def test_protokolliere_aenderung_mit_roher_connection(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(bind=eng)
    with eng.connect() as conn:
        protokolliere_aenderung(
            conn, tabelle="journal", datensatz_id=42, feld="kategorie_id",
            alter_wert=None, neuer_wert=7, migration_version=157, grund="Testgrund",
        )
        conn.commit()
        eintrag = conn.execute(text("SELECT * FROM aenderungsprotokoll")).mappings().first()
    assert eintrag["datensatz_id"] == 42
    assert eintrag["neuer_wert"] == "7"


def test_export_aenderungsprotokoll_csv(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    db = Session()
    db.add(AenderungsProtokoll(
        tabelle="journal", datensatz_id=1, feld="kategorie_id",
        alter_wert=None, neuer_wert="5", migration_version=157, grund="Testgrund",
    ))
    db.commit()

    csv_bytes, anzahl = export_aenderungsprotokoll_csv(db)

    assert anzahl == 1
    text_inhalt = csv_bytes.decode("utf-8-sig")
    assert "Testgrund" in text_inhalt
    assert "journal" in text_inhalt
