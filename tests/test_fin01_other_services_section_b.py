"""Section B — other services (SRV01/SRV02 records) on the FIN01 bill screen.

The vessel-accordion rewrite dropped this section, which left a customer whose
only outstanding work is a service record invisible in the billable-customer
picker and unbillable. Dev DB with a throwaway customer + record, cleaned up.
"""
from pathlib import Path

from database import get_db, get_cursor
from modules.FIN01 import model

GEN_BILL = Path('modules/FIN01/generate_bill.html').read_text(encoding='utf-8')
NAME = 'ZZ SECTION B CO'
RATE = 1500.0


def _setup(cur, qty=3, status='Approved', billed=0):
    cur.execute('SELECT id FROM finance_service_types WHERE is_active=1 ORDER BY id LIMIT 1')
    svc = cur.fetchone()['id']
    cur.execute('INSERT INTO vessel_customers (name) VALUES (%s) RETURNING id', [NAME])
    cid = cur.fetchone()['id']
    cur.execute("""INSERT INTO service_records
        (module_code, record_number, service_type_id, source_type, source_id,
         source_display, record_date, billable_quantity, billable_uom, doc_status, is_billed)
        VALUES ('SRV02','ZZSECB1',%s,'Customer',%s,%s,'2026-09-18',%s,'OTH',%s,%s)
        RETURNING id""", [svc, cid, NAME, qty, status, billed])
    rec = cur.fetchone()['id']
    cur.execute("""INSERT INTO customer_agreements (customer_type, customer_id, agreement_code,
        agreement_name, agreement_status, is_active, valid_from, valid_to)
        VALUES ('Customer', %s, 'ZZSECBAG', 'sec b', 'Approved', 1, '2000-01-01', NULL)
        RETURNING id""", [cid])
    ag = cur.fetchone()['id']
    cur.execute("""INSERT INTO customer_agreement_lines
        (agreement_id, service_type_id, cargo_name, rate, uom, currency_code)
        VALUES (%s, %s, NULL, %s, 'OTH', 'INR')""", [ag, svc, RATE])
    return cid, rec, ag, svc


def _teardown(cid, rec, ag, bill_id=None):
    conn = get_db(); cur = get_cursor(conn)
    if bill_id:
        for t in ('parcel_charge_billed', 'bill_vessels', 'bill_lines'):
            cur.execute('DELETE FROM ' + t + ' WHERE bill_id=%s', [bill_id])
        cur.execute('DELETE FROM bill_header WHERE id=%s', [bill_id])
    cur.execute('DELETE FROM service_records WHERE id=%s', [rec])
    cur.execute('DELETE FROM customer_agreement_lines WHERE agreement_id=%s', [ag])
    cur.execute('DELETE FROM customer_agreements WHERE id=%s', [ag])
    cur.execute('DELETE FROM vessel_customers WHERE id=%s', [cid])
    conn.commit(); conn.close()


def test_a_service_only_customer_is_billable():
    """The reported bug: no cargo, one approved service record, and the party
    never appeared in the picker."""
    conn = get_db(); cur = get_cursor(conn)
    cid, rec, ag, _ = _setup(cur)
    conn.commit(); conn.close()
    try:
        counts = model.customers_with_billables()
        assert NAME in counts, 'service-only customer missing from the picker'
        assert counts[NAME]['service_count'] == 1
        assert counts[NAME]['actual_count'] == 0 and counts[NAME]['proforma_count'] == 0
    finally:
        _teardown(cid, rec, ag)


def test_only_approved_unbilled_records_count():
    for status, billed in (('Pending', 0), ('Draft', 0), ('Approved', 1)):
        conn = get_db(); cur = get_cursor(conn)
        cid, rec, ag, _ = _setup(cur, status=status, billed=billed)
        conn.commit(); conn.close()
        try:
            assert NAME not in model.customers_with_billables(), (status, billed)
            assert model.get_unbilled_services('Customer', cid) == []
        finally:
            _teardown(cid, rec, ag)


def test_services_come_back_priced_and_shaped_like_cargo_lines():
    """The screen totals GST the same way for both, so the tax rates have to
    ride along on a service line exactly as they do on a cargo one."""
    conn = get_db(); cur = get_cursor(conn)
    cid, rec, ag, _ = _setup(cur)
    conn.commit(); conn.close()
    try:
        out = model.get_customer_billables('Customer', cid)
        assert out['vessels'] == []
        assert len(out['services']) == 1
        s = out['services'][0]
        assert s['service_record_id'] == rec
        assert s['qty'] == 3.0 and s['rate'] == RATE and s['amount'] == 4500.0
        assert s['record_number'] == 'ZZSECB1'
        for k in ('cgst_rate', 'sgst_rate', 'igst_rate', 'gst_rate_id', 'sac_code',
                  'is_tds', 'tds_percent', 'uom'):
            assert k in s, k
    finally:
        _teardown(cid, rec, ag)


def test_billing_a_service_line_needs_no_parcel_and_no_vessel():
    """A service line has neither, so the cargo-line guard must not reject it,
    and it must not write a parcel-ledger row either."""
    conn = get_db(); cur = get_cursor(conn)
    cid, rec, ag, _ = _setup(cur)
    conn.commit(); conn.close()
    bill_id = None
    try:
        s = model.get_unbilled_services('Customer', cid)[0]
        line = dict(s, quantity=s['qty'], rate=RATE,
                    tds_applicable=s['is_tds'], tds_percent=s['tds_percent'])
        bill_id, _no = model.generate_bill(
            {'customer_type': 'Customer', 'customer_id': cid, 'customer_name': NAME,
             'bill_date': '2026-09-18', 'lines': [line]},
            created_by='test', bill_status='Approved')

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("""SELECT service_record_id, cargo_source_type, quantity, line_amount
                       FROM bill_lines WHERE bill_id=%s""", [bill_id])
        bl = dict(cur.fetchone())
        assert bl['service_record_id'] == rec
        assert bl['cargo_source_type'] is None
        assert bl['line_amount'] == 4500.0
        cur.execute('SELECT COUNT(*) AS n FROM parcel_charge_billed WHERE bill_id=%s', [bill_id])
        assert cur.fetchone()['n'] == 0, 'a service line is not a parcel charge'
        cur.execute('SELECT is_billed FROM service_records WHERE id=%s', [rec])
        assert cur.fetchone()['is_billed'] == 1
        conn.close()

        # and it stops being offered
        assert model.get_unbilled_services('Customer', cid) == []
        assert NAME not in model.customers_with_billables()
    finally:
        _teardown(cid, rec, ag, bill_id)


def test_cargo_lines_still_require_a_parcel_and_vessel():
    """Relaxing the guard for service lines must not let a malformed cargo line
    through — that check is what stops an unanchored charge being billed."""
    try:
        model.generate_bill({'customer_type': 'Customer', 'customer_id': 1,
                             'lines': [{'service_type_id': 1, 'quantity': 1, 'rate': 1}]},
                            created_by='test', bill_status='Draft')
    except ValueError as e:
        assert 'cargo bill line' in str(e), e
        return
    raise AssertionError('a line with no parcel, vessel or service record was accepted')


def test_the_screen_has_section_b():
    assert 'B. Other Services' in GEN_BILL and 'A. Billable Charges by Vessel' in GEN_BILL
    assert 'renderServices' in GEN_BILL and 'servicesRoot' in GEN_BILL
    # ticked service lines reach the totals and the bill payload
    assert ".sv-chk'" in GEN_BILL and ".sv-chk:checked'" in GEN_BILL
    # and the picker label shows why the customer is listed
    assert 'service_count' in GEN_BILL


def test_cargo_and_services_are_not_mixed_on_one_bill():
    assert 'cannot go on the same bill' in GEN_BILL


def test_the_customer_picker_is_sorted_by_name():
    """Alphabetical — the operator knows which party they are billing and scans
    for the name, rather than hunting for it by how much it owes."""
    src = Path('modules/FIN01/views.py').read_text(encoding='utf-8')
    body = src[src.index('def get_customers_for_billing('):]
    body = body[:body.index('\ndef ')] if '\ndef ' in body else body
    assert "rows.sort(key=lambda r: (r['name'] or '').upper())" in body
    # the billable counts no longer drive the order, only the label
    assert 'actual_count' not in body.split('rows.sort')[1]
