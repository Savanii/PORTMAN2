"""FIN01 billables engine: cargo charges per parcel plus the per-vessel Shore
Gangway charge, vessel grouping, ledger remaining, LDUD gate. Dev DB with a
throwaway customer + VCN + LDUD + parcel, cleaned up."""
from database import get_db, get_cursor
from modules.FIN01 import model as fin


def _setup(cur, ldud_status='Closed', equipment='CRANE', toll=True):
    cur.execute("INSERT INTO vessel_customers (name) VALUES ('ENGTEST CO') RETURNING id")
    cid = cur.fetchone()['id']
    cur.execute("INSERT INTO vcn_header (operation_type, vcn_doc_num, vessel_name) "
                "VALUES ('Import','VCN-ENG-1','ENGVESSEL') RETURNING id")
    vid = cur.fetchone()['id']
    cur.execute("""INSERT INTO vcn_consigners
        (vcn_id, parcel_no, cargo_name, quantity, consigner_name, importer_name,
         pipeline_name, unload_terminal, toll_applicable, equipment_names, parcel_seq)
        VALUES (%s,'P1','OIL','100','ENGTEST CO','ENGTEST CO','PL1','T1',%s,%s,1) RETURNING id""",
        [vid, toll, equipment])
    pid = cur.fetchone()['id']
    cur.execute("INSERT INTO ldud_header (vcn_id, doc_status) VALUES (%s,%s) RETURNING id",
                [vid, ldud_status])
    return cid, vid, pid


def _teardown(cid, vid, pid):
    conn = get_db(); cur = get_cursor(conn)
    cur.execute("DELETE FROM parcel_charge_billed WHERE cargo_source_id=%s", [pid])
    cur.execute("DELETE FROM ldud_header WHERE vcn_id=%s", [vid])
    cur.execute("DELETE FROM vcn_header WHERE id=%s", [vid])  # cascades consigner
    cur.execute("DELETE FROM vessel_customers WHERE id=%s", [cid])
    conn.commit(); conn.close()


def test_four_charges_grouped_by_vessel_and_ledger_remaining():
    conn = get_db(); cur = get_cursor(conn)
    cid, vid, pid = _setup(cur, equipment='CRANE', toll=True)
    conn.commit(); conn.close()
    try:
        out = fin.get_customer_billables('Customer', cid)
        vessels = out['vessels']
        assert len(vessels) == 1
        v = vessels[0]
        assert v['vcn_id'] == vid and v['vcn_doc_num'] == 'VCN-ENG-1'
        codes = sorted(l['service_code'] for l in v['lines'])
        # four cargo charges off the parcel, plus one Shore Gangway for the vessel
        assert codes == ['CHGU01', 'INFM01', 'MLAC01', 'SHGW01', 'TOLL01'], codes
        cargo_lines = [l for l in v['lines'] if not l.get('is_vessel_charge')]
        assert all(abs(l['qty'] - 100.0) < 1e-6 for l in cargo_lines)
        gangway = next(l for l in v['lines'] if l['service_code'] == 'SHGW01')
        assert gangway['qty'] == 1.0 and gangway['is_vessel_charge'] is True
        chg = next(l for l in v['lines'] if l['service_code'] == 'CHGU01')
        assert chg['cargo_source_type'] == 'VCN_IMPORT' and chg['cargo_source_id'] == pid

        # ledger reduces remaining; fully billed CHGU01 drops out
        conn = get_db(); cur = get_cursor(conn)
        fin.record_parcel_charge(cur, 'VCN_IMPORT', pid, chg['service_type_id'],
                                 'CHGU01', 999, 100, 'tester')
        conn.commit(); conn.close()
        out2 = fin.get_customer_billables('Customer', cid)
        codes2 = sorted(l['service_code'] for l in out2['vessels'][0]['lines'])
        assert codes2 == ['INFM01', 'MLAC01', 'SHGW01', 'TOLL01'], codes2
    finally:
        _teardown(cid, vid, pid)


def test_no_equipment_no_toll_yields_two_cargo_charges():
    """Equipment and toll drop out, but Shore Gangway does not — it is charged
    for the vessel, not for what the parcel happened to need."""
    conn = get_db(); cur = get_cursor(conn)
    cid, vid, pid = _setup(cur, equipment='', toll=False)
    conn.commit(); conn.close()
    try:
        v = fin.get_customer_billables('Customer', cid)['vessels'][0]
        assert sorted(l['service_code'] for l in v['lines']) == ['CHGU01', 'INFM01', 'SHGW01']
    finally:
        _teardown(cid, vid, pid)


def test_gangway_is_charged_once_no_matter_how_many_parcels():
    """A second parcel on the same vessel must not double the vessel charge."""
    conn = get_db(); cur = get_cursor(conn)
    cid, vid, pid = _setup(cur)
    cur.execute("""INSERT INTO vcn_consigners
        (vcn_id, parcel_no, cargo_name, quantity, consigner_name, importer_name,
         pipeline_name, unload_terminal, toll_applicable, equipment_names, parcel_seq)
        VALUES (%s,'P2','OIL','50','ENGTEST CO','ENGTEST CO','PL1','T1',FALSE,'',2)
        RETURNING id""", [vid])
    pid2 = cur.fetchone()['id']
    conn.commit(); conn.close()
    try:
        v = fin.get_customer_billables('Customer', cid)['vessels'][0]
        gangway = [l for l in v['lines'] if l['service_code'] == 'SHGW01']
        assert len(gangway) == 1, [l['service_code'] for l in v['lines']]
        # both parcels still yield their own cargo charges
        assert len({l['cargo_source_id'] for l in v['lines']
                    if not l.get('is_vessel_charge')}) == 2
    finally:
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("DELETE FROM parcel_charge_billed WHERE cargo_source_id=%s", [pid2])
        conn.commit(); conn.close()
        _teardown(cid, vid, pid)


def test_draft_ldud_yields_no_vessels():
    conn = get_db(); cur = get_cursor(conn)
    cid, vid, pid = _setup(cur, ldud_status='Draft')
    conn.commit(); conn.close()
    try:
        assert fin.get_customer_billables('Customer', cid)['vessels'] == []
    finally:
        _teardown(cid, vid, pid)
