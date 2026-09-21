"""Go-live cutover.

Three jobs, all admin-only and all frozen once the cutover is locked:

  1. **Numbering seeds** — tell PORTMAN2 where the legacy system stopped, so
     the first invoice / bill / credit note it issues continues that run. A
     seed is a floor, never an assignment (see FIN01.next_from_seed).
  2. **Flagging legacy-billed work** — mark the cargo parcels *and* the service
     records the legacy system already invoiced, so PORTMAN2 never bills them
     again. Both flags say the same thing: billed, with no bill behind it — a
     `parcel_charge_billed` row with `bill_id` NULL for a parcel, and
     `is_billed=1, bill_id NULL` on a service record. Unmarking touches only
     those bill-less rows, so it can never disturb a genuine bill.
  3. **The lock** — once go-live data is final, freeze every write here.

Because the ledger is what `is_vcn_billed()` reads, flagging a parcel also
locks its VCN and its LDUD. That is the intended go-live behaviour.

The legacy `is_billed` / `billed_quantity` declaration columns are no-ops in
PORTMAN2 (see FIN01._mark_cargo_source_billed) — nothing here writes them.
"""
import json
from datetime import datetime

from database import get_db, get_cursor
from modules.FIN01 import model as fin_model

# Parcel tables the cutover works on. No MBC — it does not exist in PORTMAN2.
CARGO_SOURCES = {
    'VCN_IMPORT': {'table': 'vcn_consigners', 'qty': 'quantity'},
    'VCN_EXPORT': {'table': 'vcn_export_cargo_declaration', 'qty': 'quantity'},
}

SEED_TYPES = ('invoice', 'bill', 'fdcn')


class CutoverLocked(Exception):
    """Raised when a write is attempted after the cutover has been locked."""


# ---------------------------------------------------------------------------
# Pure helpers (no DB — unit-testable)
# ---------------------------------------------------------------------------

def validate_start_seq(value, current_max):
    """A seed must be a whole number above the current maximum. At or below it,
    the seed could hand out a number a live document already carries."""
    try:
        seq = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Start number must be a whole number')
    if seq <= 0:
        raise ValueError('Start number must be greater than zero')
    if seq <= int(current_max or 0):
        raise ValueError(f'Start number must be above the current maximum ({int(current_max or 0)})')
    return seq


def compute_partial_billed(declared, already_billed, requested=None):
    """Quantity to flag as legacy-billed: `requested` clamped to what is left of
    the declared quantity and rounded to 3dp. None/'' means all of the rest."""
    remaining = round(float(declared or 0) - float(already_billed or 0), 3)
    if remaining <= 0:
        return 0.0
    if requested in (None, ''):
        return remaining
    try:
        qty = float(requested)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a number')
    if qty <= 0:
        raise ValueError('Quantity must be greater than zero')
    return round(min(qty, remaining), 3)


# ---------------------------------------------------------------------------
# Audit + lock (the lock IS an audit entry — no extra table to keep in sync)
# ---------------------------------------------------------------------------

def write_audit(action, details, performed_by, cur=None):
    conn = None if cur is not None else get_db()
    if conn is not None:
        cur = get_cursor(conn)
    cur.execute('''INSERT INTO cutover_audit (action, details, performed_by, performed_at)
                   VALUES (%s, %s, %s, %s)''',
                [action, json.dumps(details, default=str), performed_by,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    if conn is not None:
        conn.commit()
        conn.close()


def is_locked():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("""SELECT action FROM cutover_audit WHERE action IN ('lock', 'unlock')
                   ORDER BY id DESC LIMIT 1""")
    row = cur.fetchone()
    conn.close()
    return bool(row and row['action'] == 'lock')


def set_lock(locked, performed_by):
    write_audit('lock' if locked else 'unlock', {'locked': bool(locked)}, performed_by)
    return bool(locked)


def _require_unlocked():
    if is_locked():
        raise CutoverLocked('Cutover is locked. Unlock it before making changes.')


# ---------------------------------------------------------------------------
# Numbering seeds
# ---------------------------------------------------------------------------

def current_max(seed_type, doc_series='', financial_year=''):
    """Highest sequence a live document already uses for this series."""
    conn = get_db()
    cur = get_cursor(conn)
    if seed_type == 'bill':
        cur.execute("SELECT MAX(CAST(SUBSTR(bill_number, 5) AS INTEGER)) AS max "
                    "FROM bill_header WHERE bill_number LIKE 'BILL%%'")
    elif seed_type == 'invoice':
        cur.execute('SELECT MAX(doc_series_seq) AS max FROM invoice_header '
                    'WHERE doc_series=%s AND financial_year=%s', [doc_series, financial_year])
    elif seed_type == 'fdcn':
        cur.execute('SELECT MAX(doc_series_seq) AS max FROM fdcn_header '
                    'WHERE doc_series=%s AND financial_year=%s', [doc_series, financial_year])
    else:
        conn.close()
        raise ValueError(f'Unknown seed type: {seed_type}')
    row = cur.fetchone()
    conn.close()
    return int((row and row['max']) or 0)


def get_seeds():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''SELECT seed_type, doc_series, financial_year, start_seq,
                          created_by, updated_by, updated_at
                   FROM cutover_seed ORDER BY seed_type, doc_series, financial_year''')
    seeds = [dict(r) for r in cur.fetchall()]
    conn.close()
    for s in seeds:
        s['current_max'] = current_max(s['seed_type'], s['doc_series'], s['financial_year'])
    return seeds


def _set_seed(seed_type, doc_series, financial_year, start_seq, performed_by):
    _require_unlocked()
    doc_series = (doc_series or '').strip()
    financial_year = (financial_year or '').strip()
    seq = validate_start_seq(start_seq, current_max(seed_type, doc_series, financial_year))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''INSERT INTO cutover_seed
            (seed_type, doc_series, financial_year, start_seq, created_by, updated_by, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (seed_type, doc_series, financial_year)
        DO UPDATE SET start_seq = EXCLUDED.start_seq,
                      updated_by = EXCLUDED.updated_by,
                      updated_at = EXCLUDED.updated_at''',
        [seed_type, doc_series, financial_year, seq, performed_by, performed_by, now])
    write_audit('set_seed', {'seed_type': seed_type, 'doc_series': doc_series,
                             'financial_year': financial_year, 'start_seq': seq},
                performed_by, cur=cur)
    conn.commit()
    conn.close()
    return seq


def set_invoice_seed(doc_series, financial_year, start_seq, performed_by):
    return _set_seed('invoice', doc_series, financial_year, start_seq, performed_by)


def set_bill_seed(start_seq, performed_by):
    return _set_seed('bill', 'BILL', '', start_seq, performed_by)


def set_fdcn_seed(doc_series, financial_year, start_seq, performed_by):
    return _set_seed('fdcn', doc_series, financial_year, start_seq, performed_by)


# ---------------------------------------------------------------------------
# Legacy-billed cargo
# ---------------------------------------------------------------------------

def get_cargo(customer_name):
    """Parcels payable by one party, with their ledger state.

    `cutover_flagged` marks a parcel held only by NULL-bill_id rows — those are
    the ones this module may release again."""
    rows = []
    conn = get_db()
    cur = get_cursor(conn)
    for src, meta in CARGO_SOURCES.items():
        cur.execute(f'''
            SELECT %s AS cargo_source_type, c.id, c.parcel_no, c.cargo_name,
                   c.{meta['qty']} AS quantity, c.equipment_names, c.toll_applicable,
                   h.vcn_doc_num, h.vessel_name,
                   COALESCE(l.billed, 0) AS billed,
                   COALESCE(l.cutover, 0) AS cutover_rows,
                   COALESCE(l.rows_total, 0) AS ledger_rows
            FROM {meta['table']} c
            JOIN vcn_header h ON h.id = c.vcn_id
            LEFT JOIN (
                SELECT cargo_source_id,
                       SUM(billed_quantity) AS billed,
                       COUNT(*) FILTER (WHERE bill_id IS NULL) AS cutover,
                       COUNT(*) AS rows_total
                FROM parcel_charge_billed WHERE cargo_source_type = %s
                GROUP BY cargo_source_id
            ) l ON l.cargo_source_id = c.id
            WHERE c.importer_name = %s
            ORDER BY h.vcn_doc_num, c.parcel_no
        ''', [src, src, customer_name])
        for r in cur.fetchall():
            r = dict(r)
            r['charges'] = len(fin_model.parcel_charge_codes(
                src, r['equipment_names'], r['toll_applicable']))
            r['cutover_flagged'] = bool(r['cutover_rows']) and r['cutover_rows'] == r['ledger_rows']
            rows.append(r)
    conn.close()
    return rows


def _service_ids(codes, cur):
    cur.execute('SELECT id, service_code FROM finance_service_types WHERE service_code = ANY(%s)',
                [list(codes)])
    return {r['service_code']: r['id'] for r in cur.fetchall()}


def mark_items_billed(items, performed_by):
    """Flag parcels as billed in the legacy system.

    Writes one `parcel_charge_billed` row per applicable service with `bill_id`
    NULL — billed, with no bill behind it. Never touches the legacy
    is_billed/billed_quantity columns; they are no-ops in PORTMAN2.
    """
    _require_unlocked()
    conn = get_db()
    cur = get_cursor(conn)
    today = datetime.now().strftime('%Y-%m-%d')
    marked = []
    for item in items:
        src = item.get('cargo_source_type')
        meta = CARGO_SOURCES.get(src)
        cargo_id = item.get('cargo_source_id')
        if not meta or not cargo_id:
            continue
        cur.execute(f'''SELECT {meta['qty']} AS quantity, equipment_names, toll_applicable, parcel_no
                        FROM {meta['table']} WHERE id=%s''', [cargo_id])
        parcel = cur.fetchone()
        if not parcel:
            continue
        codes = fin_model.parcel_charge_codes(src, parcel['equipment_names'],
                                              parcel['toll_applicable'])
        svc_ids = _service_ids(codes, cur)
        for code in codes:
            service_type_id = svc_ids.get(code)
            if not service_type_id:
                continue
            cur.execute('''SELECT COALESCE(SUM(billed_quantity), 0) AS q
                           FROM parcel_charge_billed
                           WHERE cargo_source_type=%s AND cargo_source_id=%s AND service_type_id=%s''',
                        [src, cargo_id, service_type_id])
            already = float(cur.fetchone()['q'] or 0)
            qty = compute_partial_billed(parcel['quantity'], already, item.get('quantity'))
            if qty <= 0:
                continue
            cur.execute('''INSERT INTO parcel_charge_billed
                    (cargo_source_type, cargo_source_id, service_type_id, service_code,
                     bill_id, billed_quantity, billed_date, created_by)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)''',
                [src, cargo_id, service_type_id, code, qty, today, performed_by])
        marked.append({'cargo_source_type': src, 'cargo_source_id': cargo_id,
                       'parcel_no': parcel['parcel_no'], 'quantity': item.get('quantity')})
    write_audit('mark_billed', {'items': marked}, performed_by, cur=cur)
    conn.commit()
    conn.close()
    return marked


def unmark_items_billed(items, performed_by):
    """Release cutover flags — deletes ONLY NULL-bill_id ledger rows, so a real
    bill's entry can never be removed here."""
    _require_unlocked()
    conn = get_db()
    cur = get_cursor(conn)
    released = []
    for item in items:
        src = item.get('cargo_source_type')
        cargo_id = item.get('cargo_source_id')
        if src not in CARGO_SOURCES or not cargo_id:
            continue
        cur.execute('''DELETE FROM parcel_charge_billed
                       WHERE cargo_source_type=%s AND cargo_source_id=%s AND bill_id IS NULL''',
                    [src, cargo_id])
        released.append({'cargo_source_type': src, 'cargo_source_id': cargo_id,
                         'rows': cur.rowcount})
    write_audit('unmark_billed', {'items': released}, performed_by, cur=cur)
    conn.commit()
    conn.close()
    return released


# ---------------------------------------------------------------------------
# Legacy-billed services
# ---------------------------------------------------------------------------
# PORTMAN2 bills service records (SRV01/SRV02) alongside cargo, so the cutover
# has to be able to flag those too — otherwise go-live re-bills every service
# the legacy system already invoiced.
#
# A service record has no quantity ledger: FIN01 marks it billed by setting
# is_billed=1 with the bill's id. The cutover flag is the same row with
# bill_id NULL — billed, with no bill behind it, exactly as for a parcel. That
# also makes unmarking safe: it only ever releases NULL-bill_id rows.


def get_services(customer_type, customer_id):
    """Approved service records for one party, with their cutover state."""
    if not customer_type or not customer_id:
        return []
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT sr.id, sr.record_number, sr.record_date, sr.billable_quantity,
               sr.billable_uom, sr.ref_source_display, sr.is_billed, sr.bill_id,
               st.service_code, st.service_name
        FROM service_records sr
        JOIN finance_service_types st ON st.id = sr.service_type_id
        WHERE sr.source_type = %s AND sr.source_id = %s
          AND sr.doc_status = 'Approved'
        ORDER BY sr.id
    ''', [customer_type, customer_id])
    rows = []
    for r in cur.fetchall():
        r = dict(r)
        r['cutover_flagged'] = bool(r['is_billed']) and r['bill_id'] is None
        # A record held by a real bill is not this module's to touch.
        r['locked_by_bill'] = bool(r['is_billed']) and r['bill_id'] is not None
        rows.append(r)
    conn.close()
    return rows


def mark_services_billed(service_ids, performed_by):
    """Flag service records as billed in the legacy system.

    Skips any record already held by a real bill — that is a genuine PORTMAN2
    billing, and overwriting its bill_id would orphan the bill line.
    """
    _require_unlocked()
    ids = [int(i) for i in (service_ids or []) if str(i).strip()]
    if not ids:
        return []
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''UPDATE service_records SET is_billed = 1, bill_id = NULL
                   WHERE id = ANY(%s) AND bill_id IS NULL
                   RETURNING id, record_number''', [ids])
    marked = [dict(r) for r in cur.fetchall()]
    write_audit('mark_services_billed',
                {'service_ids': [m['id'] for m in marked],
                 'skipped': sorted(set(ids) - {m['id'] for m in marked})},
                performed_by, cur=cur)
    conn.commit()
    conn.close()
    return marked


def unmark_services_billed(service_ids, performed_by):
    """Release cutover flags on service records — only rows with no bill behind
    them, so a real bill's record can never be reopened here."""
    _require_unlocked()
    ids = [int(i) for i in (service_ids or []) if str(i).strip()]
    if not ids:
        return []
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''UPDATE service_records SET is_billed = 0
                   WHERE id = ANY(%s) AND is_billed = 1 AND bill_id IS NULL
                   RETURNING id, record_number''', [ids])
    released = [dict(r) for r in cur.fetchall()]
    write_audit('unmark_services_billed',
                {'service_ids': [r['id'] for r in released]}, performed_by, cur=cur)
    conn.commit()
    conn.close()
    return released
