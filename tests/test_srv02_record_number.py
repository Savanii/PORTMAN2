"""SRV02 numbers records SRV1, SRV2, ... and still bills through FIN01.

SRV02 shares service_records with SRV01, so the two things worth pinning are
that the numbering does not collide with SRV01's plain integers, and that a
record made in SRV02 is picked up by billing exactly like an SRV01 one.
Uses the dev DB directly; creates throwaway rows and deletes them.
"""
from database import get_db, get_cursor, get_module_config, save_module_config
from modules.SRV01 import model as srv_model


def _svc_type_id(cur):
    cur.execute('SELECT id FROM finance_service_types ORDER BY id LIMIT 1')
    return cur.fetchone()['id']


def test_srv02_numbers_are_srv_prefixed_and_independent_of_srv01():
    cfg = get_module_config('SRV01')
    save_module_config('SRV01', dict(cfg, service_start_no=999900))
    conn = get_db(); cur = get_cursor(conn)
    svc_id = _svc_type_id(cur)
    ids = []
    try:
        # Whatever SRV01 has, SRV02 starts its own series at SRV1.
        cur.execute("INSERT INTO service_records (module_code, record_number, service_type_id, source_type, source_id) "
                    "VALUES ('SRV01', '999900', %s, 'VCN', 0) RETURNING id", [svc_id])
        ids.append(cur.fetchone()['id'])
        conn.commit()
        assert srv_model.get_next_record_number('SRV02') == 'SRV1'
        assert srv_model.get_next_record_number('SRV01') == '999901'

        cur.execute("INSERT INTO service_records (module_code, record_number, service_type_id, source_type, source_id) "
                    "VALUES ('SRV02', 'SRV1', %s, 'VCN', 0) RETURNING id", [svc_id])
        ids.append(cur.fetchone()['id'])
        conn.commit()
        assert srv_model.get_next_record_number('SRV02') == 'SRV2'
        # SRV02's rows must not push SRV01's plain counter along.
        assert srv_model.get_next_record_number('SRV01') == '999901'

        # Delete the newest and its number comes back, same as SRV01.
        cur.execute('DELETE FROM service_records WHERE id=%s', [ids.pop()])
        conn.commit()
        assert srv_model.get_next_record_number('SRV02') == 'SRV1'
    finally:
        for row_id in ids:
            cur.execute('DELETE FROM service_records WHERE id=%s', [row_id])
        conn.commit(); conn.close()
        save_module_config('SRV01', cfg)


def test_each_module_lists_only_its_own_records():
    conn = get_db(); cur = get_cursor(conn)
    svc_id = _svc_type_id(cur)
    ids = []
    try:
        for code, number in (('SRV01', '999800'), ('SRV02', 'SRV9800')):
            cur.execute("INSERT INTO service_records (module_code, record_number, service_type_id, source_type, source_id) "
                        "VALUES (%s, %s, %s, 'VCN', 0) RETURNING id", [code, number, svc_id])
            ids.append(cur.fetchone()['id'])
        conn.commit()

        one, _ = srv_model.get_service_records(size=1000, module_code='SRV01')
        two, _ = srv_model.get_service_records(size=1000, module_code='SRV02')
        assert '999800' in [r['record_number'] for r in one]
        assert '999800' not in [r['record_number'] for r in two]
        assert 'SRV9800' in [r['record_number'] for r in two]
        assert 'SRV9800' not in [r['record_number'] for r in one]
    finally:
        for row_id in ids:
            cur.execute('DELETE FROM service_records WHERE id=%s', [row_id])
        conn.commit(); conn.close()


def test_srv02_record_reaches_fin01_billing_unchanged():
    """An approved, unbilled SRV02 record shows up in the same billing pickup
    FIN01 uses for SRV01 — that query is module-blind on purpose."""
    conn = get_db(); cur = get_cursor(conn)
    svc_id = _svc_type_id(cur)
    cur.execute('SELECT id FROM vessel_customers ORDER BY id LIMIT 1')
    row = cur.fetchone()
    if not row:
        conn.close()
        return  # no customer master on this database, nothing to bill against
    cust_id = row['id']
    ids = []
    try:
        cur.execute("INSERT INTO service_records "
                    "(module_code, record_number, service_type_id, source_type, source_id, doc_status, is_billed) "
                    "VALUES ('SRV02', 'SRV9801', %s, 'Customer', %s, 'Approved', 0) RETURNING id",
                    [svc_id, cust_id])
        ids.append(cur.fetchone()['id'])
        conn.commit()

        found = srv_model.get_unbilled_records_for_customer('Customer', cust_id)
        assert 'SRV9801' in [r['record_number'] for r in found]
    finally:
        for row_id in ids:
            cur.execute('DELETE FROM service_records WHERE id=%s', [row_id])
        conn.commit(); conn.close()
