"""Smoke tests for the FINV01 SAP endpoint wiring (Task 6 fix-up).

Covers the finding: create-invoice was re-pointed at the async sap_outbound_queue,
but retry/cancel/cancellation-CN were left calling the old synchronous path
(retry_sap called an undefined `_auto_post_to_sap`; cancel/CN posted directly
via sap_client and never enqueued, so `unbill_invoice_sources` was unreachable).

No real SAP network calls are made: sap_client.post_invoice_to_sap and
sap_queue.trigger are monkeypatched, and sap_builder's payload builders (which
need SAPCFG.get_active_config) are stubbed so this doesn't depend on SAP
config being present in the dev DB.
"""
from flask import Flask
from database import get_db, get_cursor
from modules.FINV01 import views as finv
import sap_queue
import sap_builder

_app = Flask(__name__)
_app.secret_key = 'pytest-secret'


def _mk_bill(cur):
    cur.execute("INSERT INTO vessel_customers (name) VALUES ('SAPEP') RETURNING id")
    cid = cur.fetchone()['id']
    cur.execute("""INSERT INTO bill_header (bill_number, bill_date, source_type, customer_type,
                   customer_id, customer_name, subtotal, total_amount, bill_status)
                   VALUES ('BILL-SAPEP-1','2026-07-02','MULTI','Customer',%s,'SAPEP',10000,11800,'Approved')
                   RETURNING id""", [cid])
    bid = cur.fetchone()['id']
    cur.execute("SELECT id FROM finance_service_types WHERE service_code='CHGU01' LIMIT 1")
    svc_row = cur.fetchone()
    service_type_id = svc_row['id'] if svc_row else None
    cur.execute("""INSERT INTO bill_lines (bill_id, service_type_id, service_code, service_name,
                   quantity, uom, rate, line_amount, line_total)
                   VALUES (%s, %s, 'CHGU01','Cargo Handling Unloading',100,'MT',100,10000,11800)""",
                [bid, service_type_id])
    return cid, bid


def _cleanup(cid, bid, inv_id):
    conn = get_db(); cur = get_cursor(conn)
    if inv_id:
        cur.execute("DELETE FROM fdcn_lines WHERE fdcn_id IN (SELECT id FROM fdcn_header WHERE original_invoice_id=%s)", [inv_id])
        cur.execute("DELETE FROM fdcn_header WHERE original_invoice_id=%s", [inv_id])
        cur.execute("DELETE FROM invoice_lines WHERE invoice_id=%s", [inv_id])
        cur.execute("DELETE FROM invoice_bill_mapping WHERE invoice_id=%s", [inv_id])
        cur.execute("DELETE FROM sap_outbound_queue WHERE invoice_id=%s", [inv_id])
        cur.execute("DELETE FROM invoice_header WHERE id=%s", [inv_id])
    if bid:
        cur.execute("DELETE FROM bill_lines WHERE bill_id=%s", [bid])
        cur.execute("DELETE FROM bill_header WHERE id=%s", [bid])
    if cid:
        cur.execute("DELETE FROM vessel_customers WHERE id=%s", [cid])
    conn.commit(); conn.close()


def _mk_invoice(monkeypatch):
    monkeypatch.setattr(sap_queue, 'trigger', lambda: None)
    monkeypatch.setattr(sap_builder, 'build_invoice_payload', lambda h, l: {'mock': 'post'})
    conn = get_db(); cur = get_cursor(conn)
    cid, bid = _mk_bill(cur); conn.commit(); conn.close()
    inv_id = finv.create_invoice_record('Customer', cid, [bid], created_by='t')
    return cid, bid, inv_id


def test_no_stale_auto_post_symbol():
    """Task 6 root cause: retry_sap called an undefined `_auto_post_to_sap`.
    It must be gone, and the async enqueue helper must exist instead."""
    assert hasattr(finv, '_enqueue_invoice_post')
    assert not hasattr(finv, '_auto_post_to_sap')
    import inspect
    src = inspect.getsource(finv)
    assert '_auto_post_to_sap' not in src


def test_retry_sap_manual_sends_queued_job(monkeypatch):
    """retry_sap must resolve `_enqueue_invoice_post`/`sap_queue.manual_send`
    without NameError, and drive the invoice to Posted via the queue."""
    cid = bid = inv_id = None
    try:
        cid, bid, inv_id = _mk_invoice(monkeypatch)

        # create_invoice_record already queued a 'post' job; mark it failed so
        # retry_sap takes the manual_send branch (mirrors a real retry).
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("UPDATE sap_outbound_queue SET status='failed' WHERE invoice_id=%s", [inv_id])
        cur.execute("UPDATE invoice_header SET invoice_status='SAP Failed' WHERE id=%s", [inv_id])
        conn.commit(); conn.close()

        import sap_client
        monkeypatch.setattr(sap_client, 'post_invoice_to_sap',
                             lambda *a, **k: {'ok': True, 'sap_document_number': 'SAPDOC1',
                                               'message': 'posted', 'log_id': 1})

        invoice = finv.model.get_invoice_by_id(inv_id)
        with _app.test_request_context('/api/module/FINV01/invoice/retry-sap',
                                        json={'invoice_id': inv_id}):
            from flask import session
            session['user_id'] = 1
            session['username'] = 'pytest'
            session['is_admin'] = True
            resp = finv.retry_sap()

        data = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
        assert data['success'] is True
        assert data.get('sap_document_number') == 'SAPDOC1'

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("SELECT invoice_status FROM invoice_header WHERE id=%s", [inv_id])
        assert cur.fetchone()['invoice_status'] == 'Posted to SAP'
        conn.close()
    finally:
        _cleanup(cid, bid, inv_id)


def test_cancel_invoice_sap_enqueues_reversal(monkeypatch):
    """cancel_invoice_sap must route through sap_queue.enqueue('reversal', ...)
    instead of posting synchronously — this is what makes
    sap_queue._apply_reversal_success (and model.unbill_invoice_sources) reachable."""
    cid = bid = inv_id = None
    try:
        cid, bid, inv_id = _mk_invoice(monkeypatch)
        monkeypatch.setattr(sap_builder, 'build_invoice_reversal_payload',
                             lambda h, l: {'mock': 'reversal'})

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("""UPDATE invoice_header SET invoice_status='Posted to SAP',
                       sap_document_number='SAPDOC-ORIG' WHERE id=%s""", [inv_id])
        conn.commit(); conn.close()

        with _app.test_request_context('/api/module/FINV01/invoice/cancel-sap',
                                        json={'invoice_id': inv_id}):
            from flask import session
            session['user_id'] = 1
            session['username'] = 'pytest'
            session['is_admin'] = True
            resp = finv.cancel_invoice_sap()

        data = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
        assert data['success'] is True
        assert data.get('queued') is True

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("""SELECT job_type, status FROM sap_outbound_queue
                       WHERE invoice_id=%s ORDER BY id DESC LIMIT 1""", [inv_id])
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row['job_type'] == 'reversal'
    finally:
        _cleanup(cid, bid, inv_id)


def test_create_cancellation_cn_enqueues_credit_note(monkeypatch):
    """create_cancellation_cn must route through sap_queue.enqueue('credit_note', ...)
    instead of creating the FDCN row synchronously — this is what makes
    sap_queue._apply_cn_success (and model.unbill_invoice_sources) reachable."""
    cid = bid = inv_id = None
    try:
        cid, bid, inv_id = _mk_invoice(monkeypatch)
        monkeypatch.setattr(sap_builder, 'build_invoice_credit_note_payload',
                             lambda h, l: {'mock': 'credit_note'})

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("""UPDATE invoice_header SET invoice_status='Posted to SAP',
                       sap_document_number='SAPDOC-ORIG' WHERE id=%s""", [inv_id])
        conn.commit(); conn.close()

        with _app.test_request_context('/api/module/FINV01/invoice/create-cancellation-cn',
                                        json={'invoice_id': inv_id}):
            from flask import session
            session['user_id'] = 1
            session['username'] = 'pytest'
            session['is_admin'] = True
            resp = finv.create_cancellation_cn()

        data = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
        assert data['success'] is True
        assert data.get('queued') is True

        conn = get_db(); cur = get_cursor(conn)
        cur.execute("""SELECT job_type FROM sap_outbound_queue
                       WHERE invoice_id=%s ORDER BY id DESC LIMIT 1""", [inv_id])
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row['job_type'] == 'credit_note'

        # No FDCN row yet — it's only created by the worker on SAP success.
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) c FROM fdcn_header WHERE original_invoice_id=%s", [inv_id])
        assert cur.fetchone()['c'] == 0
        conn.close()
    finally:
        _cleanup(cid, bid, inv_id)


def test_manual_send_route_wired(monkeypatch):
    """The reference `sap-queue/manual-send` endpoint must exist and call
    sap_queue.manual_send (not the removed synchronous path)."""
    assert hasattr(finv, 'sap_queue_manual_send')
    monkeypatch.setattr(sap_queue, 'manual_send',
                         lambda qid: {'ok': True, 'sap_document_number': 'SAPDOC2'})

    with _app.test_request_context('/api/module/FINV01/sap-queue/manual-send',
                                    json={'queue_id': 12345}):
        from flask import session
        session['user_id'] = 1
        session['username'] = 'pytest'
        session['is_admin'] = True
        resp = finv.sap_queue_manual_send()

    data = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
    assert data['success'] is True
    assert data['sap_document_number'] == 'SAPDOC2'
