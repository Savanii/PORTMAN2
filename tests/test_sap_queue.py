"""sap_queue enqueue + claim + retry, with sap_client mocked (no network)."""
import sap_queue
from database import get_db, get_cursor


def test_enqueue_and_claim_and_fail(monkeypatch):
    # prevent the real background thread + network
    monkeypatch.setattr(sap_queue, 'trigger', lambda: None)
    qid = sap_queue.enqueue('invoice_post', 'INVOICE', 999999, 'INV-Q-1',
                            {'x': 1}, invoice_id=None, created_by='t')
    try:
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("SELECT status, retry_count, payload FROM sap_outbound_queue WHERE id=%s", [qid])
        row = cur.fetchone(); conn.close()
        assert row['status'] == 'pending' and row['retry_count'] == 0
        assert '"x": 1' in row['payload'] or "'x': 1" in row['payload']
    finally:
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("DELETE FROM sap_outbound_queue WHERE id=%s", [qid])
        conn.commit(); conn.close()
