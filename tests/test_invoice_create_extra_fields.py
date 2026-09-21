"""Invoice creation ignores request fields that are not invoice_header columns.

POST /api/module/FINV01/invoice/create merges the whole request body into the
header data, and the INSERT column list was built from those keys. The FINV01
screen posts display-only fields alongside the real ones -- doc_series_name has
been in that payload since the initial commit -- so the INSERT named a column
that does not exist and the request 500'd with:

    UndefinedColumn: column "doc_series_name" of relation "invoice_header"
    does not exist

The columns are now filtered against the real table.
"""
import pytest

from database import get_db, get_cursor
from modules.FIN01 import model


def test_only_real_columns_reach_the_insert():
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cols = model._invoice_header_columns(cur)
    finally:
        conn.close()
    assert 'invoice_number' in cols and 'total_amount' in cols
    # The field that caused the 500 is genuinely not a column.
    assert 'doc_series_name' not in cols


def test_the_columns_the_screen_sends_are_real():
    """Every override FINV01 posts that IS a column must still be accepted --
    the filter must not quietly drop things the invoice needs."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cols = model._invoice_header_columns(cur)
    finally:
        conn.close()
    for field in ('invoice_date', 'payment_terms', 'due_date', 'remarks',
                  'virtual_account_id', 'customer_name', 'customer_gstin',
                  'subtotal', 'cgst_amount', 'sgst_amount', 'igst_amount',
                  'tds_amount', 'tcs_amount', 'round_off', 'total_amount'):
        assert field in cols, f'{field} must survive the whitelist'


def test_helper_is_cached():
    conn = get_db()
    cur = get_cursor(conn)
    try:
        a = model._invoice_header_columns(cur)
        b = model._invoice_header_columns(cur)
    finally:
        conn.close()
    assert a is b, 'column list should be read once per process'
