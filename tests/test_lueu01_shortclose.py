"""Short-close behaviour for LUEU01: a flagged, timeless log row zeroes Remaining
but is excluded from the Avg flow rate, and is reversible. Uses the dev DB with a
throwaway VCN -> consigner -> LDUD -> parcel-op -> log chain, cleaned up after."""
import pytest
from database import get_db, get_cursor
from modules.LUEU01 import model


def _find(parcels, pid):
    return next(p for p in parcels if p['parcel_op_id'] == pid)


def test_shortclose_zeroes_remaining_excludes_avg_and_reverts():
    conn = get_db(); cur = get_cursor(conn)
    cur.execute("INSERT INTO vcn_header (operation_type) VALUES ('Import') RETURNING id")
    vid = cur.fetchone()['id']
    cur.execute("""INSERT INTO vcn_consigners (vcn_id, quantity, cargo_name, parcel_seq, parcel_no)
                   VALUES (%s,'1000','OIL',1,'P1') RETURNING id""", [vid])
    cid = cur.fetchone()['id']
    cur.execute("INSERT INTO ldud_header (vcn_id) VALUES (%s) RETURNING id", [vid])
    lid = cur.fetchone()['id']
    cur.execute("""INSERT INTO ldud_parcel_ops (ldud_id, parcel_ids, cargo_name, quantity)
                   VALUES (%s,%s,'OIL','1000') RETURNING id""", [lid, str(cid)])
    pid = cur.fetchone()['id']
    cur.execute("""INSERT INTO lueu_parcel_log (parcel_op_id, entry_date, from_time, to_time, quantity)
                   VALUES (%s,'2026-06-15','08:00','18:00',900)""", [pid])
    conn.commit(); conn.close()
    try:
        p = _find(model.get_started_parcels(vid), pid)
        assert abs(p['remaining_qty'] - 100.0) < 1e-6, p
        assert abs(p['avg_rate'] - 90.0) < 0.1, p          # 900 MT / 10 h
        assert p['is_shortclosed'] is False

        model.shortclose_parcel(pid, 'tester')
        p2 = _find(model.get_started_parcels(vid), pid)
        assert abs(p2['remaining_qty']) < 1e-6, p2          # Remaining -> 0
        assert abs(p2['avg_rate'] - 90.0) < 0.1, p2         # avg UNCHANGED (100 excluded)
        assert p2['is_shortclosed'] is True

        # the flagged row is timeless and carries the leftover
        conn2 = get_db(); cur2 = get_cursor(conn2)
        cur2.execute("""SELECT quantity, from_time, to_time FROM lueu_parcel_log
                        WHERE parcel_op_id=%s AND is_shortclose IS TRUE AND is_deleted IS NOT TRUE""", [pid])
        sc = cur2.fetchone(); conn2.close()
        assert sc and float(sc['quantity']) == 100.0 and sc['from_time'] is None

        # second short-close is a no-op error (nothing left)
        with pytest.raises(ValueError):
            model.shortclose_parcel(pid, 'tester')

        # revert restores remaining + avg, and clears the flag
        model.revert_shortclose(pid, 'tester')
        p3 = _find(model.get_started_parcels(vid), pid)
        assert abs(p3['remaining_qty'] - 100.0) < 1e-6, p3
        assert abs(p3['avg_rate'] - 90.0) < 0.1, p3
        assert p3['is_shortclosed'] is False

        # nothing to revert now
        with pytest.raises(ValueError):
            model.revert_shortclose(pid, 'tester')
    finally:
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("DELETE FROM lueu_parcel_log WHERE parcel_op_id=%s", [pid])
        cur.execute("DELETE FROM ldud_parcel_ops WHERE id=%s", [pid])
        cur.execute("DELETE FROM ldud_header WHERE id=%s", [lid])
        cur.execute("DELETE FROM vcn_header WHERE id=%s", [vid])  # cascades consigner
        conn.commit(); conn.close()
