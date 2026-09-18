"""VCN01 berthing delays: round-trip through the model, and the Along Side /
Cast Off bounds the UI validates against. Dev DB directly, like the other
VCN01 tests; the throwaway header is deleted at the end (ON DELETE CASCADE
clears the rows)."""
from database import get_db, get_cursor
from modules.VCN01 import model


def _new_vcn():
    conn = get_db(); cur = get_cursor(conn)
    cur.execute("INSERT INTO vcn_header (operation_type) VALUES ('Import') RETURNING id")
    vcn_id = cur.fetchone()['id']
    conn.commit(); conn.close()
    return vcn_id


def test_berth_delay_save_update_delete():
    vcn_id = _new_vcn()
    try:
        row_id = model.save_berth_delay({'vcn_id': vcn_id, 'port_type': 'Port',
                                         'service_type': 'Marine',
                                         'delay_start': '2026-01-01T10:00',
                                         'delay_end': '2026-01-01T14:30'})
        row = model.get_berth_delays(vcn_id)[0]
        assert row['id'] == row_id
        assert (row['port_type'], row['service_type']) == ('Port', 'Marine')
        assert row['delay_start'] == '2026-01-01T10:00'

        model.save_berth_delay({'id': row_id, 'vcn_id': vcn_id, 'port_type': 'Non Port',
                                'service_type': 'Operations',
                                'delay_start': '2026-01-01T10:00', 'delay_end': ''})
        row = model.get_berth_delays(vcn_id)[0]
        assert (row['port_type'], row['service_type']) == ('Non Port', 'Operations')
        assert row['delay_end'] is None   # blank end clears, doesn't store ''

        model.delete_berth_delay(row_id)
        assert model.get_berth_delays(vcn_id) == []
    finally:
        model.delete_header(vcn_id)


def test_delay_window_carries_the_berthing_bounds():
    vcn_id = _new_vcn()
    conn = get_db(); cur = get_cursor(conn)
    cur.execute("""INSERT INTO ldud_header (vcn_id, anchored_datetime, pilot_pickup_time,
                   alongside_datetime, cast_off_datetime) VALUES (%s,%s,%s,%s,%s)""",
                (vcn_id, '2026-01-01T06:00', '2026-01-01T09:00',
                 '2026-01-01T10:00', '2026-01-02T18:00'))
    conn.commit(); conn.close()
    try:
        w = model.get_delay_window(vcn_id)
        assert w['anchored'] == '2026-01-01T06:00'      # pre-berthing window intact
        assert w['pilot_pickup'] == '2026-01-01T09:00'
        assert w['alongside'] == '2026-01-01T10:00'
        assert w['cast_off'] == '2026-01-02T18:00'
    finally:
        conn = get_db(); cur = get_cursor(conn)
        cur.execute('DELETE FROM ldud_header WHERE vcn_id=%s', (vcn_id,))
        conn.commit(); conn.close()
        model.delete_header(vcn_id)


def test_berth_delays_stay_out_of_the_grid_total():
    """Total Delay on the VCN grid is the pre-berthing table only — berthing
    delays live in their own table so RP01's vcn_delays reports don't move."""
    vcn_id = _new_vcn()
    try:
        model.save_berth_delay({'vcn_id': vcn_id, 'port_type': 'Port', 'service_type': 'Marine',
                                'delay_start': '2026-01-01T10:00', 'delay_end': '2026-01-01T14:30'})
        rows, _ = model.get_data(page=1, size=200)
        assert next(r for r in rows if r['id'] == vcn_id)['total_delay_mins'] == 0
    finally:
        model.delete_header(vcn_id)
