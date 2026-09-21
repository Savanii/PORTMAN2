"""TDS is computed whenever the service master says it applies.

It used to be computed only inside:

    if not data.get('tds_applicable') and svc.get('is_tds'):

— i.e. only when the caller said *nothing* about TDS. But the billing screen
always posts tds_applicable from that same master and never posts an amount,
so the branch was skipped exactly when TDS applied and tds_amount stayed 0.
TCS never had the bug: it is computed unconditionally from its rate.

TDS is now derived alongside TCS, from the settled line amount.

Hits the dev DB; every row it writes is removed again.
"""
import pytest

from database import get_db, get_cursor
from modules.FIN01 import model


@pytest.fixture
def bill():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('SELECT id FROM vessel_customers ORDER BY id LIMIT 1')
    row = cur.fetchone()
    if not row:
        conn.close()
        pytest.skip('no customers in this database')
    cur.execute("""INSERT INTO bill_header
        (bill_number, bill_date, customer_type, customer_id, customer_name,
         customer_gstin, customer_gst_state_code, bill_status)
        VALUES ('PYTEST-TDS', CURRENT_DATE::text, 'Customer', %s, 'pytest',
                '27ABCDE1234F1Z5', '27', 'Draft') RETURNING id""", [row['id']])
    bill_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    yield bill_id
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('DELETE FROM bill_lines WHERE bill_id=%s', [bill_id])
    cur.execute('DELETE FROM bill_header WHERE id=%s', [bill_id])
    conn.commit()
    conn.close()


def _tds_service(cur):
    cur.execute("""SELECT id, tds_percent FROM finance_service_types
                   WHERE is_tds = 1 AND COALESCE(tds_percent, 0) > 0
                   ORDER BY id LIMIT 1""")
    return cur.fetchone()


def _line(bill_id, svc_id, **over):
    data = {'bill_id': bill_id, 'service_type_id': svc_id, 'service_name': 'pytest',
            'service_description': 'pytest', 'quantity': 1000, 'uom': 'MT',
            'rate': 100, 'line_amount': 100000,
            'customer_gstin': '27ABCDE1234F1Z5', 'customer_state_code': '27'}
    data.update(over)
    return data


def _stored(bill_id):
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute("""SELECT line_amount, tds_applicable, tds_percent, tds_amount
                       FROM bill_lines WHERE bill_id=%s ORDER BY id DESC LIMIT 1""", [bill_id])
        return dict(cur.fetchone())
    finally:
        conn.close()


def test_tds_is_computed_when_the_screen_sends_applicable_and_rate(bill):
    """The payload the billing screen actually sends: applicable + percent,
    no amount. This is the case that produced 0.00."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        svc = _tds_service(cur)
    finally:
        conn.close()
    if not svc:
        pytest.skip('no TDS-enabled service configured')

    pct = float(svc['tds_percent'])
    model.save_bill_line(_line(bill, svc['id'], tds_applicable=1, tds_percent=pct))
    row = _stored(bill)
    assert float(row['tds_amount']) == round(100000 * pct / 100, 2)


def test_tds_is_computed_from_the_master_when_the_caller_says_nothing(bill):
    """The other path must keep working -- the master alone is enough."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        svc = _tds_service(cur)
    finally:
        conn.close()
    if not svc:
        pytest.skip('no TDS-enabled service configured')

    model.save_bill_line(_line(bill, svc['id']))
    row = _stored(bill)
    assert row['tds_applicable'] == 1
    assert float(row['tds_amount']) == round(100000 * float(svc['tds_percent']) / 100, 2)


def test_tds_is_on_the_basic_not_the_gst(bill):
    """18% GST on the line must not enter the TDS base."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        svc = _tds_service(cur)
    finally:
        conn.close()
    if not svc:
        pytest.skip('no TDS-enabled service configured')

    model.save_bill_line(_line(bill, svc['id'], tds_applicable=1, tds_percent=2))
    row = _stored(bill)
    assert float(row['tds_amount']) == 2000.00        # 2% of 100000
    assert float(row['tds_amount']) != 2360.00        # not 2% of 118000


def test_an_explicit_amount_from_the_caller_wins(bill):
    """A corrected figure passed in is not recomputed away."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        svc = _tds_service(cur)
    finally:
        conn.close()
    if not svc:
        pytest.skip('no TDS-enabled service configured')

    model.save_bill_line(_line(bill, svc['id'], tds_applicable=1,
                              tds_percent=2, tds_amount=1234.56))
    assert float(_stored(bill)['tds_amount']) == 1234.56


def test_tds_does_not_reduce_the_bill_total(bill):
    """TDS is the customer's own withholding at payment time -- the bill is
    raised gross, which is what SAP and the IRP are both told."""
    conn = get_db()
    cur = get_cursor(conn)
    try:
        svc = _tds_service(cur)
    finally:
        conn.close()
    if not svc:
        pytest.skip('no TDS-enabled service configured')

    model.save_bill_line(_line(bill, svc['id'], tds_applicable=1, tds_percent=2))
    conn = get_db()
    cur = get_cursor(conn)
    try:
        totals = model.recalc_bill_totals(cur, bill)
        conn.commit()
    finally:
        conn.close()
    assert float(totals['tds_amount']) == 2000.00
    assert float(totals['total_amount']) == 118000.00
