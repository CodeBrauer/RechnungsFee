"""
Regressionstest für Issue #389: ZUGFeRD-Mapping verwechselte bei Positionen mit
Menge != 1 den Nettoeinzelpreis (rechnungspositionen.netto, seit Migration 139 ein
reiner Stückpreis) mit der Positionssumme (rechnungspositionen.brutto/.ust_betrag,
seit Migration 139 bereits Menge-multipliziert). Betroffen: NetPriceProductTradePrice
(BT-146, wurde zusätzlich fälschlich nochmal durch die Menge geteilt), die
Line-Zeilensumme (BT-131) sowie darüber alle Kopfsummen BT-106/BT-109/BT-112/BT-115,
die aus derselben (falschen) Basis gebildet werden. Von ask4it gemeldet.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from database.models import Rechnung, Rechnungsposition
from utils.zugferd import generate_zugferd_xml

UNTERNEHMEN = {
    "firmenname": "Testfirma GmbH",
    "strasse": "Teststraße", "hausnummer": "1", "plz": "12345", "ort": "Teststadt",
    "land": "DE", "steuernummer": "12/345/67890", "ust_idnr": "",
    "ist_kleinunternehmer": False,
}


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _rechnung_mit_menge(db, menge: Decimal, einzelpreis: Decimal, ust_satz: Decimal) -> Rechnung:
    netto_gesamt = einzelpreis * menge
    ust_betrag = (netto_gesamt * ust_satz / 100).quantize(Decimal("0.01"))
    brutto = netto_gesamt + ust_betrag
    r = Rechnung(
        typ="ausgang", rechnungsnummer="RE-1", datum=date(2026, 7, 1),
        netto_gesamt=netto_gesamt, ust_gesamt=ust_betrag, brutto_gesamt=brutto,
        ist_entwurf=False,
    )
    db.add(r)
    db.flush()
    db.add(Rechnungsposition(
        rechnung_id=r.id, position_nr=1, beschreibung="Beratung", menge=menge,
        einheit="Stück", netto=einzelpreis, ust_satz=ust_satz, ust_betrag=ust_betrag,
        brutto=brutto,
    ))
    db.commit()
    db.refresh(r)
    return r


def test_line_net_price_ist_stueckpreis_nicht_durch_menge_geteilt():
    """BT-146 (NetPriceProductTradePrice) muss der Nettoeinzelpreis bleiben - nicht
    nochmal durch die Menge geteilt (rechnungspositionen.netto ist bereits der
    Stückpreis, seit Migration 139)."""
    db = _db()
    rechnung = _rechnung_mit_menge(db, menge=Decimal("3"), einzelpreis=Decimal("100.00"), ust_satz=Decimal("19"))

    xml = generate_zugferd_xml(rechnung, UNTERNEHMEN).decode("utf-8")

    assert "<ram:ChargeAmount>100.00</ram:ChargeAmount>" in xml


def test_line_total_amount_ist_menge_mal_einzelpreis():
    """BT-131 (Line-Zeilensumme) muss Menge x Nettoeinzelpreis sein, nicht nur der
    Einzelpreis."""
    db = _db()
    rechnung = _rechnung_mit_menge(db, menge=Decimal("3"), einzelpreis=Decimal("100.00"), ust_satz=Decimal("19"))

    xml = generate_zugferd_xml(rechnung, UNTERNEHMEN).decode("utf-8")

    assert "<ram:LineTotalAmount>300.00</ram:LineTotalAmount>" in xml


def test_kopfsummen_beruecksichtigen_menge():
    """BT-106 (LineTotalAmount), BT-109 (TaxBasisTotalAmount), BT-112 (GrandTotalAmount)
    und BT-115 (DuePayableAmount) müssen auf Basis der Positionssumme (Menge x
    Einzelpreis), nicht auf Basis der Summe der Einzelpreise berechnet werden."""
    db = _db()
    rechnung = _rechnung_mit_menge(db, menge=Decimal("3"), einzelpreis=Decimal("100.00"), ust_satz=Decimal("19"))

    xml = generate_zugferd_xml(rechnung, UNTERNEHMEN).decode("utf-8")

    assert "<ram:LineTotalAmount>300.00</ram:LineTotalAmount>" in xml
    assert "<ram:TaxBasisTotalAmount>300.00</ram:TaxBasisTotalAmount>" in xml
    assert "<ram:GrandTotalAmount>357.00</ram:GrandTotalAmount>" in xml
    assert "<ram:DuePayableAmount>357.00</ram:DuePayableAmount>" in xml
