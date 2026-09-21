"""The Cutover tab lists only parties it can actually act on.

The picker used to render the whole customer master (45 rows here); picking any
of them but one showed two empty tables. It now lists parties holding cargo
parcels or approved service records.

Hits the dev DB like the rest of this suite.
"""
import pytest

from database import get_db, get_cursor
from modules.ADMIN import cutover


def _names(customer_type):
    return {p['name'] for p in cutover.get_parties(customer_type)}


def test_only_parties_with_something_to_flag_are_listed():
    parties = cutover.get_parties('Customer')
    assert parties, 'expected at least one customer with cargo or services'
    # Every row justifies its place in the dropdown.
    for p in parties:
        assert p['parcels'] or p['services'], p


def test_the_full_master_is_not_returned():
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('SELECT COUNT(*) AS n FROM vessel_customers')
        master = cur.fetchone()['n']
    finally:
        conn.close()
    assert len(cutover.get_parties('Customer')) < master


def test_a_party_with_no_cargo_or_services_is_absent():
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('''
            SELECT c.name FROM vessel_customers c
            WHERE NOT EXISTS (SELECT 1 FROM vcn_consigners v
                              WHERE v.importer_name = c.name
                                AND COALESCE(v.is_removed, FALSE) = FALSE)
              AND NOT EXISTS (SELECT 1 FROM vcn_export_cargo_declaration e
                              WHERE e.importer_name = c.name
                                AND COALESCE(e.is_removed, FALSE) = FALSE)
              AND NOT EXISTS (SELECT 1 FROM service_records s
                              WHERE s.source_type = 'Customer' AND s.source_id = c.id
                                AND s.doc_status = 'Approved')
            LIMIT 1''')
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip('every customer in this database has cargo or services')
    assert row['name'] not in _names('Customer')


def test_unknown_party_type_returns_nothing():
    # The master table name is interpolated into the SQL, so anything not on
    # the whitelist must fall out before it gets there.
    assert cutover.get_parties('Bogus') == []
    assert cutover.get_parties(None) == []
    assert cutover.get_parties("'; DROP TABLE bill_header; --") == []


def test_a_cutover_flagged_party_is_still_listed():
    """Flagging a parcel must not remove its party from the picker — otherwise
    the flag could never be reopened. The flag lives in parcel_charge_billed,
    never on the parcel, so the party still qualifies."""
    parties = cutover.get_parties('Customer')
    if not parties:
        pytest.skip('no party with cargo in this database')
    name = next((p['name'] for p in parties if p['parcels']), None)
    if not name:
        pytest.skip('no party with cargo parcels in this database')

    parcel = cutover.get_cargo(name)[0]
    item = {'cargo_source_type': parcel['cargo_source_type'],
            'cargo_source_id': parcel['id']}
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cutover.mark_items_billed([item], 'pytest-cutover')
        flagged = [c for c in cutover.get_cargo(name) if c['id'] == parcel['id']][0]
        assert flagged['cutover_flagged'] is True
        assert name in _names('Customer'), 'flagged party dropped out of the picker'
    finally:
        cutover.unmark_items_billed([item], 'pytest-cutover')
        cur.execute("DELETE FROM cutover_audit WHERE performed_by = 'pytest-cutover'")
        conn.commit()
        conn.close()

    restored = [c for c in cutover.get_cargo(name) if c['id'] == parcel['id']][0]
    assert restored['cutover_flagged'] is False
