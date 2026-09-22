"""
Regressionstest für Migration 161 (Issue #400-Folgefund):
buche_vorlage() (Buchungsvorlagen - "Wiederkehrende Buchung" für Miete/Leasing/Abonnements)
kannte den Kleinunternehmerstatus bislang nicht. Bei einer Ausgabe wurde daraus ein
unzulässiger echter Vorsteuerabzug abgeleitet (journal.vorsteuer_betrag fließt direkt in
EÜR-Zeile 57 ein), bei einer Einnahme konnte fälschlich USt ausgewiesen werden. Diese
Journaleinträge sind ab Erstellung GoBD-unveränderlich - die Migration korrigiert
Bestandsdaten einmalig, wenn das Unternehmen als Kleinunternehmer hinterlegt ist.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import main
from database.connection import Base
from database.models import Journaleintrag, Kategorie, Unternehmen


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def _kategorie(name="Büromiete", kontenart="Aufwand") -> Kategorie:
    return Kategorie(name=name, kontenart=kontenart, konto_skr03="4210", konto_skr04="6310", ust_satz_standard=19)


def test_buchungsvorlagen_journaleintraege_bei_kleinunternehmer_korrigiert(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)

    with eng.connect() as con:
        unt = Unternehmen(
            firmenname="Test GmbH", strasse="Teststr.", hausnummer="1", plz="12345", ort="Testort",
            ist_kleinunternehmer=True,
        )
        kat = _kategorie()
        s = Session(bind=con)
        s.add_all([unt, kat])
        s.commit()

        # Ausgabe (Miete) ueber eine Buchungsvorlage: Vorsteuerabzug faelschlich gewaehrt.
        ausgabe = Journaleintrag(
            datum=date(2026, 1, 1), belegnr="BV-1", beschreibung="Büromiete Januar",
            kategorie_id=kat.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("19.00"), vorsteuerabzug=True, brutto_betrag=Decimal("119.00"),
            buchungsvorlage_id=1,
        )
        # Einnahme (Abo-Erlös) ueber eine Buchungsvorlage: USt faelschlich ausgewiesen.
        einnahme = Journaleintrag(
            datum=date(2026, 1, 1), belegnr="BV-2", beschreibung="Abo-Erlös Januar",
            kategorie_id=None, zahlungsart="Bank", art="Einnahme",
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("0"), vorsteuerabzug=False, brutto_betrag=Decimal("119.00"),
            konto_ust_skr03="1776", konto_ust_skr04="3806", buchungsvorlage_id=2,
        )
        # Kontrolle: manuelle Journal-Buchung (kein buchungsvorlage_id) - darf NICHT angefasst
        # werden, die §19-Sperre in _felder_aus_data() greift dort schon seit Issue #397.
        manuell = Journaleintrag(
            datum=date(2026, 1, 1), belegnr="BV-3", beschreibung="Manuelle Ausgabe",
            kategorie_id=kat.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("19.00"), vorsteuerabzug=True, brutto_betrag=Decimal("119.00"),
        )
        s.add_all([ausgabe, einnahme, manuell])
        s.commit()
        ausgabe_id, einnahme_id, manuell_id = ausgabe.id, einnahme.id, manuell.id
        s.close()

        con.execute(text("PRAGMA user_version = 160"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        def _zeile(id_):
            return con.execute(
                text("""SELECT ust_satz, ust_betrag, vorsteuer_betrag, vorsteuerabzug, netto_betrag,
                        brutto_betrag, konto_ust_skr03, konto_ust_skr04 FROM journal WHERE id = :id"""),
                {"id": id_},
            ).fetchone()

        a = _zeile(ausgabe_id)
        e = _zeile(einnahme_id)
        m = _zeile(manuell_id)
        protokoll_count = con.execute(
            text("SELECT COUNT(*) FROM aenderungsprotokoll WHERE migration_version = 161")
        ).scalar()

    # Ausgabe: Vorsteuerabzug zurückgenommen, Zahlbetrag/USt-Satz/-Betrag unangetastet (real).
    assert a.vorsteuerabzug == 0
    assert a.vorsteuer_betrag == 0
    assert a.ust_satz == 19
    assert a.ust_betrag == 19.00
    assert a.brutto_betrag == 119.00

    # Einnahme: keine USt mehr, Netto = Brutto, Zahlbetrag unangetastet.
    assert e.ust_satz == 0
    assert e.ust_betrag == 0
    assert e.netto_betrag == 119.00
    assert e.brutto_betrag == 119.00
    assert e.konto_ust_skr03 is None
    assert e.konto_ust_skr04 is None

    # Manuelle Buchung ohne buchungsvorlage_id bleibt unangetastet.
    assert m.vorsteuerabzug == 1
    assert m.vorsteuer_betrag == 19.00

    # Ausgabe: 1 Feld (vorsteuer_betrag) korrigiert; Einnahme: 3 Felder (netto/ust_satz/ust_betrag).
    assert protokoll_count == 4
    assert main.SCHEMA_VERSION >= 161


def test_ohne_kleinunternehmer_bleiben_buchungsvorlagen_journaleintraege_unveraendert(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)

    with eng.connect() as con:
        unt = Unternehmen(
            firmenname="Test GmbH", strasse="Teststr.", hausnummer="1", plz="12345", ort="Testort",
            ist_kleinunternehmer=False,
        )
        kat = _kategorie()
        s = Session(bind=con)
        s.add_all([unt, kat])
        s.commit()

        ausgabe = Journaleintrag(
            datum=date(2026, 1, 1), belegnr="BV-1", beschreibung="Büromiete Januar",
            kategorie_id=kat.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("19"), ust_betrag=Decimal("19.00"),
            vorsteuer_betrag=Decimal("19.00"), vorsteuerabzug=True, brutto_betrag=Decimal("119.00"),
            buchungsvorlage_id=1,
        )
        s.add(ausgabe)
        s.commit()
        ausgabe_id = ausgabe.id
        s.close()

        con.execute(text("PRAGMA user_version = 160"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        a = con.execute(
            text("SELECT vorsteuerabzug, vorsteuer_betrag FROM journal WHERE id = :id"),
            {"id": ausgabe_id},
        ).fetchone()

    assert a.vorsteuerabzug == 1
    assert a.vorsteuer_betrag == 19.00
