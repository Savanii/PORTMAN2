"""FINV01 invoice create from a bill: header + lines + bill mapping, numbered.
Uses a throwaway customer + bill; no SAP network (enqueue is fine — it only
inserts a queue row; monkeypatch trigger to avoid the thread)."""
import pytest
from database import get_db, get_cursor
from modules.FINV01 import views as finv


def _mk_bill(cur):
    cur.execute("INSERT INTO vessel_customers (name) VALUES ('INVC') RETURNING id")
    cid = cur.fetchone()['id']
    cur.execute("""INSERT INTO bill_header (bill_number, bill_date, source_type, customer_type,
                   customer_id, customer_name, subtotal, total_amount, bill_status)
                   VALUES ('BILL-INV-1','2026-07-02','MULTI','Customer',%s,'INVC',10000,11800,'Approved')
                   RETURNING id""", [cid])
    bid = cur.fetchone()['id']
    # service_type_id is NOT NULL on bill_lines — CHGU01 (Cargo Handling Unloading)
    # exists in finance_service_types as id 2 in the dev seed data.
    cur.execute("""SELECT id FROM finance_service_types WHERE service_code='CHGU01' LIMIT 1""")
    svc_row = cur.fetchone()
    service_type_id = svc_row['id'] if svc_row else None
    cur.execute("""INSERT INTO bill_lines (bill_id, service_type_id, service_code, service_name,
                   quantity, uom, rate, line_amount, line_total)
                   VALUES (%s, %s, 'CHGU01','Cargo Handling Unloading',100,'MT',100,10000,11800)""",
                [bid, service_type_id])
    return cid, bid


def test_create_invoice_from_bill(monkeypatch):
    import sap_queue
    monkeypatch.setattr(sap_queue, 'trigger', lambda: None)
    conn = get_db(); cur = get_cursor(conn)
    cid, bid = _mk_bill(cur); conn.commit(); conn.close()
    inv_id = None
    try:
        # call the model-level create used by the /invoice/create endpoint.
        inv_id = finv.create_invoice_record('Customer', cid, [bid], created_by='t')
        conn = get_db(); cur = get_cursor(conn)
        cur.execute("SELECT invoice_number FROM invoice_header WHERE id=%s", [inv_id])
        assert cur.fetchone()['invoice_number']
        cur.execute("SELECT COUNT(*) c FROM invoice_bill_mapping WHERE invoice_id=%s", [inv_id])
        assert cur.fetchone()['c'] == 1
        cur.execute("SELECT COUNT(*) c FROM invoice_lines WHERE invoice_id=%s", [inv_id])
        assert cur.fetchone()['c'] >= 1
        conn.close()
    finally:
        conn = get_db(); cur = get_cursor(conn)
        if inv_id:
            cur.execute("DELETE FROM invoice_lines WHERE invoice_id=%s", [inv_id])
            cur.execute("DELETE FROM invoice_bill_mapping WHERE invoice_id=%s", [inv_id])
            cur.execute("DELETE FROM sap_outbound_queue WHERE invoice_id=%s", [inv_id])
            cur.execute("DELETE FROM invoice_header WHERE id=%s", [inv_id])
        cur.execute("DELETE FROM bill_lines WHERE bill_id=%s", [bid])
        cur.execute("DELETE FROM bill_header WHERE id=%s", [bid])
        cur.execute("DELETE FROM vessel_customers WHERE id=%s", [cid])
        conn.commit(); conn.close()
