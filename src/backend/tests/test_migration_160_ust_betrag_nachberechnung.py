"""
Regressionstest für Migration 160 (Issue #372, Folgefund nach Migration 159):
journal.ust_satz/ust_betrag/vorsteuer_betrag bzw. die gleichnamigen Felder in
vorsteuer_ansprueche werden bei §13b-Alt-Buchungen additiv nachberechnet, wenn sie
noch auf 0 stehen - Migration 159 hatte nur das ust_sonderfall-Tag nachgetragen, nicht
die Beträge. Von Uwe Koslowski gemeldet und bestätigt: nur 19% betroffen, nur
Dienstleistungs-Kategorien (13b_abs1/13b_abs2), keine ig_erwerb-Alt-Buchungen.

Bewusst NICHT angefasst: ig_erwerb (0% ist dort ein legitimer Fall, eigene KZ 90) und
einfuhr_ust (dort ist der Betrag ein manuell eingetragener Festwert, kein Prozentsatz -
ust_satz_standard steht dort bewusst auf 0, wodurch der Guard "k.ust_satz_standard > 0"
diese Kategorie automatisch ausschließt).
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import main
from database.connection import Base
from database.models import Journaleintrag, Kategorie, Rechnung, VorsteuerAnspruch


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_13b_alt_buchung_bekommt_ust_und_vorsteuer_nachberechnet(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)

    with eng.connect() as con:
        kat_13b = Kategorie(
            name="Drittland-Dienstleistungen (§13b Abs. 2)", kontenart="Aufwand",
            konto_skr03="3125", konto_skr04="5925", ust_sonderfall="13b_abs2", ust_satz_standard=19,
        )
        kat_ig = Kategorie(
            name="Wareneinkauf EU", kontenart="Aufwand", konto_skr03="3425", konto_skr04="5425",
            ust_sonderfall="ig_erwerb", ust_satz_standard=19,
        )
        kat_einfuhr = Kategorie(
            name="Einfuhrumsatzsteuer (Zoll/DHL)", kontenart="Aufwand",
            konto_skr03="1588", konto_skr04="1433", ust_sonderfall="einfuhr_ust", ust_satz_standard=0,
        )
        rechnung = Rechnung(
            typ="eingang", rechnungsnummer="ER-1", datum=date(2026, 1, 10),
            brutto_gesamt=Decimal("300.00"), netto_gesamt=Decimal("300.00"), ist_entwurf=False,
        )
        s = Session(bind=con)
        s.add_all([kat_13b, kat_ig, kat_einfuhr, rechnung])
        s.commit()

        # Betroffene Alt-Buchung: §13b getaggt (bereits durch Migration 159), aber USt/Vorsteuer
        # noch auf 0 - der urspruengliche Fehlerzustand.
        betroffen = Journaleintrag(
            datum=date(2026, 1, 10), belegnr="ER-1", beschreibung="Anthropic API",
            kategorie_id=kat_13b.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("300.00"), ust_satz=Decimal("0"), ust_betrag=Decimal("0"),
            vorsteuer_betrag=Decimal("0"), brutto_betrag=Decimal("300.00"),
            ust_sonderfall="13b_abs2", rechnung_id=rechnung.id,
        )
        # ig_erwerb mit echtem 0%-Satz - darf NICHT angefasst werden.
        ig_null = Journaleintrag(
            datum=date(2026, 1, 11), belegnr="ER-2", beschreibung="EU-Wareneinkauf 0%",
            kategorie_id=kat_ig.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("100.00"), ust_satz=Decimal("0"), ust_betrag=Decimal("0"),
            vorsteuer_betrag=Decimal("0"), brutto_betrag=Decimal("100.00"),
            ust_sonderfall="ig_erwerb",
        )
        # einfuhr_ust mit Betrag 0 (noch keine DHL-Nachforderung) - darf NICHT angefasst werden.
        einfuhr_null = Journaleintrag(
            datum=date(2026, 1, 12), belegnr="ER-3", beschreibung="Einfuhr ohne EUSt",
            kategorie_id=kat_einfuhr.id, zahlungsart="Bank", art="Ausgabe",
            netto_betrag=Decimal("0"), ust_satz=Decimal("0"), ust_betrag=Decimal("0"),
            vorsteuer_betrag=Decimal("0"), brutto_betrag=Decimal("0"),
            ust_sonderfall="einfuhr_ust",
        )
        betroffen_vst = VorsteuerAnspruch(
            rechnung_id=rechnung.id, datum=date(2026, 1, 10), kategorie_id=kat_13b.id,
            netto_betrag=Decimal("300.00"), ust_satz=Decimal("0"), ust_betrag=Decimal("0"),
            vorsteuer_betrag=Decimal("0"), ust_sonderfall="13b_abs2", typ="anspruch",
        )
        s.add_all([betroffen, ig_null, einfuhr_null, betroffen_vst])
        s.commit()
        betroffen_id, ig_id, einfuhr_id, vst_id = betroffen.id, ig_null.id, einfuhr_null.id, betroffen_vst.id
        s.close()

        con.execute(text("PRAGMA user_version = 159"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        def _zeile(tabelle, id_, mit_brutto=True):
            felder = "ust_satz, ust_betrag, vorsteuer_betrag, netto_betrag" + (", brutto_betrag" if mit_brutto else "")
            return con.execute(
                text(f"SELECT {felder} FROM {tabelle} WHERE id = :id"),
                {"id": id_},
            ).fetchone()

        j = _zeile("journal", betroffen_id)
        ig = _zeile("journal", ig_id)
        einfuhr = _zeile("journal", einfuhr_id)
        v = _zeile("vorsteuer_ansprueche", vst_id, mit_brutto=False)
        protokoll_count = con.execute(
            text("SELECT COUNT(*) FROM aenderungsprotokoll WHERE migration_version = 160")
        ).scalar()

    # Betroffene Zeile: USt/Vorsteuer additiv nachberechnet, Zahlbetrag unangetastet.
    assert j[0] == 19  # ust_satz
    assert j[1] == 57.00  # ust_betrag = 300 * 19%
    assert j[2] == 57.00  # vorsteuer_betrag = ust_betrag (100% abziehbar bei Reverse Charge)
    assert j[3] == 300.00  # netto_betrag unveraendert
    assert j[4] == 300.00  # brutto_betrag unveraendert (Zahlbetrag!)

    # ig_erwerb mit echtem 0%-Satz bleibt unangetastet.
    assert ig[0] == 0
    assert ig[1] == 0
    assert ig[2] == 0

    # einfuhr_ust bleibt unangetastet (kein Prozentsatz-Fall).
    assert einfuhr[0] == 0
    assert einfuhr[1] == 0
    assert einfuhr[2] == 0

    # vorsteuer_ansprueche-Pendant ebenso korrigiert.
    assert v[0] == 19
    assert v[1] == 57.00
    assert v[2] == 57.00

    # 2 betroffene Zeilen (journal + vorsteuer_ansprueche) x 3 Felder = 6 Protokolleintraege.
    assert protokoll_count == 6
    assert main.SCHEMA_VERSION >= 160
