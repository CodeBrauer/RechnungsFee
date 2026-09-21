"""
Regressionstest für Migration 162 (Issue #399, Wunsch 1): Der bisher fest im Code hinterlegte
"RE-"/"ER-"-Präfix wandert für Bestandsinstallationen ins Nummernkreis-Format, damit sich am
sichtbaren Ergebnis nichts ändert - aber NUR für Nummernkreise, die noch exakt auf dem alten
Auslieferungszustand "YY####" stehen. Wer das Format bereits selbst angepasst hatte, wird nicht
angefasst, sonst würde die Migration genau den in Issue #399 beschriebenen Fehler reproduzieren
(eigenes Format zusätzlich mit RE- verfälschen statt entfälschen).
"""
from pathlib import Path

from sqlalchemy import create_engine, text

import main
from database.connection import Base


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_pristine_default_wird_auf_re_er_gehoben(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    with eng.connect() as con:
        con.execute(text(
            "INSERT INTO nummernkreise (typ, bezeichnung, format, naechste_nr, reset_jaehrlich, aktiv) "
            "VALUES ('rechnung_ausgang', 'Ausgangsrechnungen', 'YY####', 1, 1, 1)"
        ))
        con.execute(text(
            "INSERT INTO nummernkreise (typ, bezeichnung, format, naechste_nr, reset_jaehrlich, aktiv) "
            "VALUES ('rechnung_eingang', 'Eingangsrechnungen', 'YY####', 1, 1, 1)"
        ))
        con.execute(text("PRAGMA user_version = 161"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        formate = dict(con.execute(text("SELECT typ, format FROM nummernkreise")).fetchall())

    assert formate["rechnung_ausgang"] == "RE-YY####"
    assert formate["rechnung_eingang"] == "ER-YY####"
    assert main.SCHEMA_VERSION >= 162


def test_bereits_angepasstes_format_bleibt_unangetastet(tmp_path, monkeypatch):
    """Genau das Szenario aus dem Issue: eine eigene Konvention wie R###-YYYY darf die
    Migration nicht zusätzlich mit RE- verfälschen."""
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    with eng.connect() as con:
        con.execute(text(
            "INSERT INTO nummernkreise (typ, bezeichnung, format, naechste_nr, reset_jaehrlich, aktiv) "
            "VALUES ('rechnung_ausgang', 'Ausgangsrechnungen', 'R###-YYYY', 7, 1, 1)"
        ))
        con.execute(text("PRAGMA user_version = 161"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        format_ausgang = con.execute(
            text("SELECT format FROM nummernkreise WHERE typ = 'rechnung_ausgang'")
        ).scalar()

    assert format_ausgang == "R###-YYYY"


def test_neuer_nummernkreis_fuer_wiederkehrende_rechnungen_wird_geseedet(tmp_path, monkeypatch):
    """seed_nummernkreise() (nicht die versionierte Migration) ergänzt den neuen Typ auch auf
    einer Bestands-DB, analog zum bestehenden Muster für z.B. 'lieferschein'."""
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    with eng.connect() as con:
        con.execute(text("DELETE FROM nummernkreise WHERE typ = 'rechnung_wiederkehrend'"))
        con.execute(text("PRAGMA user_version = 161"))
        con.commit()

    from database.seed import seed_nummernkreise
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=eng)
    seed_nummernkreise(Session())

    with eng.connect() as con:
        row = con.execute(
            text("SELECT format, aktiv, naechste_nr FROM nummernkreise WHERE typ = 'rechnung_wiederkehrend'")
        ).fetchone()

    assert row is not None
    assert row[0] == "DA-YY####"
    assert row[1] == 0  # standardmaessig inaktiv - gemeinsamer Kreis bleibt Default
