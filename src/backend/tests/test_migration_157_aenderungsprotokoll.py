"""
Regressionstest für Migration 157 (Issue #385): aenderungsprotokoll-Tabelle.
"""
from pathlib import Path

from sqlalchemy import create_engine, text

import main
from database.connection import Base


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_bestehende_db_erhaelt_aenderungsprotokoll_tabelle(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    with eng.connect() as con:
        con.execute(text("DROP TABLE aenderungsprotokoll"))
        con.execute(text("PRAGMA user_version = 156"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        tabelle = con.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='aenderungsprotokoll'")
        ).fetchone()
        spalten = {r[1] for r in con.execute(text("PRAGMA table_info(aenderungsprotokoll)")).fetchall()}

    assert tabelle is not None
    assert spalten == {
        "id", "tabelle", "datensatz_id", "feld", "alter_wert", "neuer_wert",
        "migration_version", "grund", "erstellt_am",
    }
    assert main.SCHEMA_VERSION >= 157


def test_trigger_blockieren_update_und_delete(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    main._setup_gobd_triggers()

    with eng.connect() as con:
        con.execute(text("""
            INSERT INTO aenderungsprotokoll
                (tabelle, datensatz_id, feld, alter_wert, neuer_wert, migration_version, grund)
            VALUES ('journal', 1, 'kategorie_id', NULL, '5', 157, 'Test')
        """))
        con.commit()

        import pytest
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError, match="unveränderbar"):
            con.execute(text("UPDATE aenderungsprotokoll SET grund = 'geändert' WHERE id = 1"))
            con.commit()

        con.rollback()

        with pytest.raises(IntegrityError, match="können nicht gelöscht werden"):
            con.execute(text("DELETE FROM aenderungsprotokoll WHERE id = 1"))
            con.commit()
