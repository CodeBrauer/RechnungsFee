"""
GoBD-Änderungsprotokoll (Issue #385).

Nachweis für nachträgliche Software-Eingriffe (Migrationen) auf bereits versiegelte
(immutable) Zeilen in journal/vorsteuer_ansprueche/tagesabschluesse - siehe
database/models.py::AenderungsProtokoll für den vollständigen Kontext.

Deckt bewusst NICHT normale Nutzerkorrekturen ab - die laufen über den Storno-Weg und
sind dadurch bereits im Journal selbsterklärend sichtbar.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


def protokolliere_aenderung(
    verbindung: "Connection | Session",
    *,
    tabelle: str,
    datensatz_id: int,
    feld: str,
    alter_wert,
    neuer_wert,
    migration_version: int,
    grund: str,
) -> None:
    """Schreibt einen Eintrag ins Änderungsprotokoll. Funktioniert sowohl mit einer
    rohen SQLAlchemy-Connection (typischer Kontext in _run_migrations()) als auch mit
    einer ORM-Session (typischer Kontext in _migrate_signaturen()) - beide unterstützen
    .execute(text(...), params).
    """
    verbindung.execute(
        text("""
            INSERT INTO aenderungsprotokoll
                (tabelle, datensatz_id, feld, alter_wert, neuer_wert, migration_version, grund)
            VALUES
                (:tabelle, :datensatz_id, :feld, :alter_wert, :neuer_wert, :migration_version, :grund)
        """),
        {
            "tabelle": tabelle,
            "datensatz_id": datensatz_id,
            "feld": feld,
            "alter_wert": None if alter_wert is None else str(alter_wert),
            "neuer_wert": None if neuer_wert is None else str(neuer_wert),
            "migration_version": migration_version,
            "grund": grund,
        },
    )
