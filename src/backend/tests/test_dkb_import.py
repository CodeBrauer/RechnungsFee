"""
Regressionstest für Issue #398 (Bank-Import DKB: UTF-8-BOM + Metazeilen).

Deckt zwei unabhängige Bugs ab, die beide zu "0 Transaktionen" führten:
  - Ein UTF-8-BOM wurde nicht entfernt, weil das DKB-Template eine fest hinterlegte
    encoding ("UTF-8" statt "utf-8-sig") hat, die gegen die BOM-fähige Erkennung gewinnt.
    Das BOM landete dadurch als sichtbares Zeichen vor dem ersten Spaltennamen, wodurch der
    Feldabgleich für jede Zeile fehlschlug.
  - Ein echter DKB-Export stellt der Spaltenüberschrift eine Anzahl Metazeilen voran
    (Kontobezeichnung, Kontostand), die zwischen Exports variieren kann - das Template hatte
    dafür ein starres skip_rows=0 hinterlegt.
"""
import json
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

import csv as csv_mod

from database.seed import SYSTEM_BANK_TEMPLATES
from utils.bank_csv_parser import find_best_template, parse_csv_mit_template


def _dkb_template(**overrides) -> SimpleNamespace:
    tpl = next(t for t in SYSTEM_BANK_TEMPLATES if t["id"] == "dkb")
    felder = {
        "column_mapping": json.dumps({"__erkennungs__": tpl["erkennungs_spalten"], **tpl["column_mapping"]}),
        "delimiter": tpl["delimiter"],
        "encoding": tpl["encoding"],
        "decimal_separator": tpl["decimal_separator"],
        "date_format": tpl["date_format"],
        "skip_rows": tpl["skip_rows"],
    }
    felder.update(overrides)
    return SimpleNamespace(**felder)


DKB_HEADER = (
    '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
    '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"'
)
DKB_ZEILE_1 = (
    '"21.09.2026";"21.09.2026";"Gebucht";"Max Mustermann";"Testfirma GmbH";"Rechnung 123";'
    '"Ueberweisung";"DE12345678901234567890";"-119,00";"";"";""'
)
DKB_ZEILE_2 = (
    '"22.09.2026";"22.09.2026";"Gebucht";"Testfirma GmbH";"Max Mustermann";"Rechnung 124";'
    '"Ueberweisung";"DE12345678901234567890";"250,00";"";"";""'
)

# Originaler, unveränderter DKB-Export mit Metazeilen vor der Spaltenüberschrift
DKB_EXPORT_MIT_METAZEILEN = (
    '"DKB-Business";"DE12345678901234567890"\n'
    ' \n'
    '"Kontostand vom 21.09.2026";"1.234,56 €"\n'
    '""\n'
    f'{DKB_HEADER}\n{DKB_ZEILE_1}\n{DKB_ZEILE_2}\n'
)


def test_dkb_export_mit_bom_und_metazeilen_wird_korrekt_geparst():
    """Voller Reproduktionsfall aus Issue #398: echter DKB-Export inkl. BOM."""
    raw = b"\xef\xbb\xbf" + DKB_EXPORT_MIT_METAZEILEN.encode("utf-8")
    template = _dkb_template()  # skip_rows=0 wie im Seed, obwohl der Export 4 Metazeilen hat

    transaktionen, _ = parse_csv_mit_template(raw, template)

    assert len(transaktionen) == 2
    assert transaktionen[0]["datum"] == date(2026, 9, 21)
    assert transaktionen[0]["betrag"] == Decimal("-119.00")
    assert transaktionen[0]["partner_name"] == "Max Mustermann"
    assert transaktionen[1]["datum"] == date(2026, 9, 22)
    assert transaktionen[1]["betrag"] == Decimal("250.00")


def test_dkb_bom_ohne_metazeilen_wird_korrekt_geparst():
    """Manueller Testfall aus dem Issue: Kopfzeilen entfernt, Header direkt in Zeile 1."""
    csv_text = f"{DKB_HEADER}\n{DKB_ZEILE_1}\n"
    raw_mit_bom = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
    raw_ohne_bom = csv_text.encode("utf-8")
    template = _dkb_template()

    tx_mit_bom, _ = parse_csv_mit_template(raw_mit_bom, template)
    tx_ohne_bom, _ = parse_csv_mit_template(raw_ohne_bom, template)

    assert len(tx_ohne_bom) == 1  # Kontrollfall, funktionierte schon vorher
    assert len(tx_mit_bom) == 1   # war vorher 0 Treffer (Issue #398)


def test_dkb_auto_erkennung_findet_template_trotz_metazeilen():
    """Die Template-Auto-Erkennung beim Datei-Upload darf sich nicht auf Zeile 1 beschränken."""
    raw = b"\xef\xbb\xbf" + DKB_EXPORT_MIT_METAZEILEN.encode("utf-8")
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    templates = [_dkb_template()]
    templates[0].id = "dkb"

    gefunden = None
    for zeile in lines[:20]:
        header = next(csv_mod.reader([zeile], delimiter=";", quotechar='"'), [])
        gefunden = find_best_template(header, templates)
        if gefunden:
            break

    assert gefunden is not None
    assert gefunden.id == "dkb"


def test_ing_mit_bereits_korrektem_skip_rows_bleibt_unveraendert():
    """Regressionsschutz: ein Template mit korrekt konfiguriertem skip_rows (ING: 13
    Metazeilen) darf durch den neuen Header-Fallback nicht verändert werden."""
    tpl = next(t for t in SYSTEM_BANK_TEMPLATES if t["id"] == "ing")
    metazeilen = "\n".join(f"Metazeile {i}" for i in range(tpl["skip_rows"]))
    header = "Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Betrag;Glaeubiger ID;Mandats ID;IBAN"
    zeile = "21.09.2026;21.09.2026;Testfirma GmbH;Ueberweisung;Rechnung 123;-119,00;;;DE12345678901234567890"
    csv_text = f"{metazeilen}\n{header}\n{zeile}\n"

    template = SimpleNamespace(
        column_mapping=json.dumps({"__erkennungs__": tpl["erkennungs_spalten"], **tpl["column_mapping"]}),
        delimiter=tpl["delimiter"],
        encoding=tpl["encoding"],
        decimal_separator=tpl["decimal_separator"],
        date_format=tpl["date_format"],
        skip_rows=tpl["skip_rows"],
    )

    transaktionen, _ = parse_csv_mit_template(csv_text.encode(tpl["encoding"]), template)

    assert len(transaktionen) == 1
    assert transaktionen[0]["betrag"] == Decimal("-119.00")
