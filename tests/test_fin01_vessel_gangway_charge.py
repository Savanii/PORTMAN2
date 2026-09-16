"""Shore Gangway (SHGW01) on the billables screen: one flat charge per vessel
for the payer, priced from the customer agreement, and gone once billed.

Creates a throwaway agreement + rate against real data on the dev DB and
removes them again.
"""
from pathlib import Path

from database import get_db, get_cursor
from modules.FIN01 import model

GEN_BILL = Path('modules/FIN01/generate_bill.html').read_text(encoding='utf-8')
RATE = 2500.0


def _payer_with_vessels(cur):
    """A customer who actually has billable parcels, or None on an empty DB."""
    counts = model.customers_with_billables()
    for name in counts:
        cur.execute('SELECT id FROM vessel_customers WHERE name=%s', [name])
        row = cur.fetchone()
        if row:
            return row['id'], name
    return None, None


def _shgw_id(cur):
    cur.execute("SELECT id FROM finance_service_types WHERE service_code='SHGW01'")
    row = cur.fetchone()
    return row['id'] if row else None


CODE = 'ZZGANGWAY'


def _agreement_with_gangway_rate(cur, conn, customer_id):
    """A throwaway approved agreement pricing SHGW01. agreement_code is unique,
    so clear any row a previously failed run left behind first."""
    _drop_agreement(cur, conn)
    cur.execute('''INSERT INTO customer_agreements
        (customer_type, customer_id, agreement_code, agreement_name, agreement_status,
         is_active, valid_from, valid_to)
        VALUES ('Customer', %s, %s, 'Gangway test', 'Approved', 1, '2000-01-01', NULL)
        RETURNING id''', [customer_id, CODE])
    agreement_id = cur.fetchone()['id']
    cur.execute('''INSERT INTO customer_agreement_lines
        (agreement_id, service_type_id, cargo_name, rate, uom, currency_code)
        VALUES (%s, %s, NULL, %s, 'OTH', 'INR')''', [agreement_id, _shgw_id(cur), RATE])
    conn.commit()
    return agreement_id


def _drop_agreement(cur, conn, agreement_id=None):
    cur.execute('''DELETE FROM customer_agreement_lines WHERE agreement_id IN
                   (SELECT id FROM customer_agreements WHERE agreement_code=%s)''', [CODE])
    cur.execute('DELETE FROM customer_agreements WHERE agreement_code=%s', [CODE])
    conn.commit()


def test_one_gangway_line_per_vessel_priced_from_the_agreement():
    conn = get_db(); cur = get_cursor(conn)
    cid, name = _payer_with_vessels(cur)
    if not cid:
        conn.close()
        return                      # no billable data on this database
    agreement_id = _agreement_with_gangway_rate(cur, conn, cid)
    try:
        vessels = model.get_customer_billables('Customer', cid)['vessels']
        assert vessels, f'{name} should have billable vessels'
        for v in vessels:
            gangway = [l for l in v['lines'] if l['service_code'] == 'SHGW01']
            assert len(gangway) == 1, (v['vcn_doc_num'], len(gangway))
            g = gangway[0]
            assert g['qty'] == 1.0                       # flat, never per parcel
            assert g['rate'] == RATE                     # from the agreement
            assert g['amount'] == RATE
            assert g['is_vessel_charge'] is True
            assert not g['cargo_name'] and not g['parcel_no']
            # last in the list, after every cargo charge
            assert v['lines'][-1]['service_code'] == 'SHGW01'
    finally:
        _drop_agreement(cur, conn)
        conn.close()


def test_gangway_disappears_once_the_vessel_is_billed():
    """The charge rides the vessel's first parcel in parcel_charge_billed, so
    the same ledger that stops a cargo charge recurring stops this one."""
    conn = get_db(); cur = get_cursor(conn)
    cid, _ = _payer_with_vessels(cur)
    if not cid:
        conn.close()
        return
    agreement_id = _agreement_with_gangway_rate(cur, conn, cid)
    shgw = _shgw_id(cur)
    try:
        v = model.get_customer_billables('Customer', cid)['vessels'][0]
        g = [l for l in v['lines'] if l['service_code'] == 'SHGW01'][0]
        cur.execute('''INSERT INTO parcel_charge_billed
            (cargo_source_type, cargo_source_id, service_type_id, service_code,
             bill_id, billed_quantity, created_by)
            VALUES (%s, %s, %s, 'SHGW01', 0, 1, 'test')''',
            [g['cargo_source_type'], g['cargo_source_id'], shgw])
        conn.commit()

        again = model.get_customer_billables('Customer', cid)['vessels']
        same = [x for x in again if x['vcn_id'] == v['vcn_id']][0]
        assert not [l for l in same['lines'] if l['service_code'] == 'SHGW01'], \
            'gangway should not be offered twice for the same vessel'
        # the cargo charges on that vessel are untouched
        assert [l for l in same['lines'] if l['service_code'] != 'SHGW01']
    finally:
        cur.execute("DELETE FROM parcel_charge_billed WHERE bill_id=0 AND service_code='SHGW01'")
        conn.commit()
        _drop_agreement(cur, conn)
        conn.close()


def test_gangway_is_not_a_parcel_charge():
    """parcel_charge_codes drives the per-parcel picker counts and Admin
    Cutover — a vessel charge in there would multiply by the parcel count."""
    for src in ('VCN_IMPORT', 'VCN_EXPORT'):
        codes = model.parcel_charge_codes(src, 'crane', True)
        assert 'SHGW01' not in codes, codes


def test_screen_marks_vessel_charges_instead_of_showing_blanks():
    """A gangway row has no parcel, no cargo and no LUEU01 logbook — the screen
    must not render it as a cargo row with missing data."""
    assert 'is_vessel_charge' in GEN_BILL
    # the "no LUEU01 log" warning is suppressed for it
    assert '!l.is_vessel_charge' in GEN_BILL
    # and its quantity is fixed
    assert "l.is_vessel_charge ? 'readonly' : ''" in GEN_BILL
