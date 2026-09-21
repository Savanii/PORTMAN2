"""Billing refuses a party with no SAP customer code.

The SAP payload's Customer_Code comes from the master's sap_customer_code
(sap_builder._get_customer_sap_info). Bills raised from the billables screen
carry no customer_gl_code, so when the master field is blank the documented
fallback is blank too and the invoice posts to SAP with no customer on it.

Hits the dev DB; every write is reverted.
"""
import pytest

from database import get_db, get_cursor
from modules.FIN01 import model


@pytest.fixture
def customer():
    """A real customer id, with its sap_customer_code restored afterwards."""
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('SELECT id, sap_customer_code FROM vessel_customers ORDER BY id LIMIT 1')
    row = cur.fetchone()
    if not row:
        conn.close()
        pytest.skip('no customers in this database')
    original = row['sap_customer_code']
    yield conn, cur, row['id']
    cur.execute('UPDATE vessel_customers SET sap_customer_code = %s WHERE id = %s',
                [original, row['id']])
    conn.commit()
    conn.close()


def _set(conn, cur, cid, code):
    cur.execute('UPDATE vessel_customers SET sap_customer_code = %s WHERE id = %s', [code, cid])
    conn.commit()


def test_a_code_lets_billing_through(customer):
    conn, cur, cid = customer
    _set(conn, cur, cid, '0010001234')
    assert model.sap_customer_code_error('Customer', cid) is None


def test_no_code_is_refused_and_names_the_master(customer):
    conn, cur, cid = customer
    _set(conn, cur, cid, None)
    err = model.sap_customer_code_error('Customer', cid)
    assert err
    assert 'VCUM01' in err, 'the message must say where to fix it'


def test_empty_string_is_refused(customer):
    conn, cur, cid = customer
    _set(conn, cur, cid, '')
    assert model.sap_customer_code_error('Customer', cid)


def test_whitespace_only_is_refused(customer):
    """'   ' is not a SAP code. It would sail through a plain falsy check and
    reach SAP as a blank Customer_Code."""
    conn, cur, cid = customer
    _set(conn, cur, cid, '   ')
    assert model.sap_customer_code_error('Customer', cid)


def test_agent_master_is_named_for_agents():
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('SELECT id FROM vessel_agents ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip('no agents in this database')
    err = model.sap_customer_code_error('Agent', row['id'])
    if err:
        assert 'VAM01' in err


def test_unknown_type_and_missing_party_are_refused():
    assert model.sap_customer_code_error('Nope', 1)
    assert model.sap_customer_code_error('Customer', None)
    assert model.sap_customer_code_error('Customer', 9999999)


def test_every_customer_type_sap_builder_knows_is_covered():
    """A type sap_builder can build a payload for must be one this guard can
    check, or that party would slip past billing unvalidated."""
    import sap_builder
    assert set(sap_builder._CUSTOMER_TABLE_MAP) <= set(model._SAP_CODE_MASTERS)
    for ctype, table in sap_builder._CUSTOMER_TABLE_MAP.items():
        assert model._SAP_CODE_MASTERS[ctype][0] == table
