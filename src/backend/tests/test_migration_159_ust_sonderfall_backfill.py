"""
Regressionstest für Migration 159 (Issue #372): journal.ust_sonderfall /
vorsteuer_ansprueche.ust_sonderfall werden bei Alt-Buchungen (vor Migration 153/375)
aus der verknüpften Kategorie nachgetragen, wenn sie NULL sind, obwohl die Kategorie
längst ein gesetztes kategorien.ust_sonderfall trägt.

Migration 153 hatte hier nur Zeilen korrigiert, die bereits fälschlich '13b_abs1'
gespeichert hatten - echte NULL-Alt-Buchungen blieben liegen (von Uwe Koslowski
gemeldet, gefunden über 6 sichtbare Drittland-Journalbuchungen die in der UStVA
nirgends auftauchten).
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

import main
from database.connection import Base
from database.models import AenderungsProtokoll, Journaleintrag, Kategorie, Rechnung, VorsteuerAnspruch


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_alt_buchungen_erhalten_ust_sonderfall_aus_kategorie(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)

    with eng.connect() as con:
        kat = Kategorie(
            name="Drittland-Dienstleistungen (§13b Abs. 2)", kontenart="Aufwand",
            konto_skr03="3125", konto_skr04="5925", ust_sonderfall="13b_abs2",
        )
        kat_normal = Kategorie(name="Bürobedarf", kontenart="Aufwand", konto_skr03="4930", konto_skr04="6815")
        rechnung = Rechnung(
            typ="eingang", rechnungsnummer="ER-1", datum=date(2026, 1, 10),
            brutto_gesamt=Decimal("119.00"), netto_gesamt=Decimal("100.00"), ist_entwurf=False,
        )
        from sqlalchemy.orm import Session
        s = Session(bind=con)
        s.add_all([kat, kat_normal, rechnung])
        s.commit()

        # Alt-Journalbuchung: kategorie_id gesetzt (Sonderfall-Kategorie), ust_sonderfall
        # aber NULL - genau der Zustand vor diesem Fix.
        alt_journal = Journaleintrag(
            datum=date(2026, 1, 10), belegnr="ER-1", beschreibung="Anthropic API",
            kategorie_id=kat.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("100.00"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("19.00"), brutto_betrag=Decimal("119.00"),
            rechnung_id=rechnung.id,
        )
        # Normale Buchung ohne Sonderfall - darf NICHT angefasst werden.
        normale_journal = Journaleintrag(
            datum=date(2026, 1, 11), belegnr="ER-2", beschreibung="Büromaterial",
            kategorie_id=kat_normal.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("50.00"), ust_betrag=Decimal("9.50"),
            vorsteuer_betrag=Decimal("9.50"), brutto_betrag=Decimal("59.50"),
        )
        alt_vorsteuer = VorsteuerAnspruch(
            rechnung_id=rechnung.id, datum=date(2026, 1, 10), kategorie_id=kat.id,
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("19.00"), typ="anspruch",
        )
        s.add_all([alt_journal, normale_journal, alt_vorsteuer])
        s.commit()
        journal_id = alt_journal.id
        normale_id = normale_journal.id
        vorsteuer_id = alt_vorsteuer.id
        s.close()

        con.execute(text("PRAGMA user_version = 158"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        j = con.execute(text("SELECT ust_sonderfall FROM journal WHERE id = :id"), {"id": journal_id}).scalar()
        j_normal = con.execute(text("SELECT ust_sonderfall FROM journal WHERE id = :id"), {"id": normale_id}).scalar()
        v = con.execute(text("SELECT ust_sonderfall FROM vorsteuer_ansprueche WHERE id = :id"), {"id": vorsteuer_id}).scalar()
        protokoll_count = con.execute(
            text("SELECT COUNT(*) FROM aenderungsprotokoll WHERE feld = 'ust_sonderfall'")
        ).scalar()

    assert j == "13b_abs2"
    assert j_normal is None
    assert v == "13b_abs2"
    assert protokoll_count == 2
    assert main.SCHEMA_VERSION >= 159
