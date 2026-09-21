"""The invoice prints 'A/C <consignee>' under the billed party, like the
pro forma does.

The invoice goes to whoever the VCN names as paying, on account of whoever the
cargo is consigned to. One vessel can carry parcels for several consignees
under one payer, so this is a list — and it follows the parcels actually on the
invoice.

Mirrors FIN01.views._parcel_consignees, which does the same for the pro forma.
"""
import pytest

from database import get_db, get_cursor
from modules.FINV01.views import _invoice_consignees, _PARCEL_TABLES


def test_both_parcel_tables_are_covered():
    """A consignee on an export parcel must show up too — missing a table
    would silently drop an A/C line rather than fail."""
    assert set(_PARCEL_TABLES) == {'VCN_IMPORT', 'VCN_EXPORT'}


def test_the_consignee_column_exists_on_both_tables():
    """VCN01 labels it Consignee; the tables call it consigner_name. If that
    ever diverges the A/C line goes blank, so pin it."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        for table in _PARCEL_TABLES.values():
            cur.execute("""SELECT 1 FROM information_schema.columns
                           WHERE table_name = %s AND column_name = 'consigner_name'""",
                        [table])
            assert cur.fetchone(), f'{table}.consigner_name is missing'
    finally:
        conn.close()


def test_an_invoice_with_no_parcels_has_no_ac_lines():
    """A service-only invoice has no cargo, so nothing to be 'on account of'."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        assert _invoice_consignees(cur, -1) == []
    finally:
        conn.close()


def test_consignees_are_unique_and_in_line_order():
    """Two parcels for different consignees under one payer produce two A/C
    lines, in the order the lines appear; a repeated consignee appears once."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('''
            SELECT ibm.invoice_id
            FROM invoice_bill_mapping ibm
            JOIN bill_lines bl ON bl.bill_id = ibm.bill_id
            WHERE bl.cargo_source_type IS NOT NULL
            GROUP BY ibm.invoice_id
            HAVING COUNT(DISTINCT bl.cargo_source_id) > 1
            LIMIT 1''')
        row = cur.fetchone()
        if not row:
            pytest.skip('no multi-parcel invoice in this database')
        names = _invoice_consignees(cur, row['invoice_id'])
        assert len(names) == len(set(names)), 'a consignee was listed twice'
        assert all(n and n.strip() for n in names), 'blank A/C line'
    finally:
        conn.close()
