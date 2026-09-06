"""
Regressionstest für Migration 158 (Issue #383): ZUGFeRD-Anhänge.
"""
from pathlib import Path

from sqlalchemy import create_engine, text

import main
from database.connection import Base


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_bestehende_db_erhaelt_zugferd_anhaenge_spalte_und_tabelle(tmp_path, monkeypatch):
    db_path = tmp_path / "alt.db"
    eng = make_engine(db_path)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "DB_PATH", db_path)

    Base.metadata.create_all(bind=eng)
    with eng.connect() as con:
        con.execute(text("DROP TABLE rechnung_zugferd_anhaenge"))
        con.execute(text("PRAGMA user_version = 157"))
        con.commit()

    main._run_migrations()

    with eng.connect() as con:
        unt_info = {r[1] for r in con.execute(text("PRAGMA table_info(unternehmen)")).fetchall()}
        tabelle = con.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='rechnung_zugferd_anhaenge'")
        ).fetchone()

    assert "zugferd_anhaenge_aktiv" in unt_info
    assert tabelle is not None
    assert main.SCHEMA_VERSION >= 158
