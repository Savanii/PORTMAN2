from flask import render_template, session, redirect, url_for, request, jsonify, Response
from functools import wraps
import csv, io
from . import bp
from database import get_db, get_cursor, get_user_permissions

MODULE_CODE = 'RP01'


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_perms():
    if session.get('is_admin'):
        return {'can_read': 1, 'can_add': 1, 'can_edit': 1, 'can_delete': 1}
    return get_user_permissions(session.get('user_id'), MODULE_CODE)


@bp.route('/module/RP01/')
@login_required
def index():
    return render_template('rp01.html', username=session.get('username'))


# ══════════════════════════════════════════════════════════════════
#  Historical MIS data — base dataset for reports.
#  Upload is a full replace: DELETE all rows, INSERT the file. Never upsert.
# ══════════════════════════════════════════════════════════════════

# CSV template header → mis_history column, in file order
MIS_COLUMNS = [
    ('Fin Year',                           'fin_year'),
    ('Month JSW',                          'month_jsw'),
    ('Month JNPT',                         'month_jnpt'),
    ('VCN No',                             'vcn_no'),
    ('Vessel Name',                        'vessel_name'),
    ('Customer',                           'customer'),
    ('Payment By',                         'payment_by'),
    ('Category',                           'category'),
    ('Sub Category',                       'sub_category'),
    ('Cargo Class',                        'cargo_class'),
    ('Cargo Name',                         'cargo_name'),
    ('Terminal',                           'terminal'),
    ('Quantity MT',                        'quantity'),
    ('Overseas/Coastal',                   'overseas_coastal'),
    ('Import/Export',                      'import_export'),
    ('Cargo Handling Rate',                'cargo_rate'),
    ('Cargo Handling Amount',              'cargo_amount'),
    ('Infra & Misc Rate',                  'infra_rate'),
    ('Infra & Misc Amount',                'infra_amount'),
    ('Toll Rate',                          'toll_rate'),
    ('Toll Amount',                        'toll_amount'),
    ('Gangway Agent',                      'gangway_agent'),
    ('Gangway Amount',                     'gangway_amount'),
    ('MLA Rate',                           'mla_rate'),
    ('MLA Amount',                         'mla_amount'),
    ('Remarks',                            'remarks'),
    ('Importer',                           'importer'),
]
DB_COLS = [c for _, c in MIS_COLUMNS]

# Vessel-level cells: filled on the first row of a vessel group in the legacy
# sheet, blank on continuation rows — inherit from the row above on ingest.
FFILL_COLS = {'fin_year', 'month_jsw', 'month_jnpt', 'vcn_no', 'vessel_name'}
NUM_COLS = {'quantity', 'cargo_rate', 'cargo_amount', 'infra_rate', 'infra_amount',
            'toll_rate', 'toll_amount', 'gangway_amount', 'mla_rate', 'mla_amount'}


def _clean(val):
    """Trim; treat #N/A / lone dashes (Excel leftovers) as blank."""
    val = (val or '').strip()
    return '' if val.upper() == '#N/A' or val.strip('- ') == '' else val


def _num(val):
    val = _clean(val).replace(',', '').replace(' ', '')
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        raise ValueError(f'not a number: {val!r}')


def parse_mis_csv(text):
    """Parse an uploaded template CSV → (rows, errors).

    Rows without a Customer are skipped: monthly subtotal rows, grand totals
    and blank rows all lack one, and per the users totals are never uploaded —
    reports compute them.
    """
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {(f or '').strip().lower(): f for f in (reader.fieldnames or [])}
    header_map, missing = {}, []
    for hdr, col in MIS_COLUMNS:
        actual = fieldnames.get(hdr.strip().lower())
        if actual is None:
            missing.append(hdr)
        else:
            header_map[col] = actual
    if missing:
        return [], ['Missing columns: ' + ', '.join(missing) + ' — please re-download the template.']

    rows, errors, carry = [], [], {}
    for line_no, r in enumerate(reader, start=2):
        raw = {col: _clean(r.get(header_map[col])) for col in DB_COLS}
        if not raw['customer']:
            continue  # subtotal / blank / junk row
        for col in FFILL_COLS:
            if raw[col]:
                carry[col] = raw[col]
            else:
                raw[col] = carry.get(col, '')
        row = {}
        for col in DB_COLS:
            try:
                row[col] = _num(raw[col]) if col in NUM_COLS else (raw[col] or None)
            except ValueError as e:
                errors.append(f'Row {line_no} [{col}]: {e}')
        if not row.get('vcn_no') or not row.get('vessel_name'):
            errors.append(f'Row {line_no}: missing VCN No / Vessel Name')
        rows.append(row)
    return rows, errors


@bp.route('/module/RP01/mis-history/')
@login_required
def mis_history_page():
    perms = get_perms()
    if not perms.get('can_read'):
        return render_template('no_access.html'), 403
    return render_template('mis_history.html', permissions=perms)


@bp.route('/api/module/RP01/mis-history/template')
@login_required
def mis_template():
    si = io.StringIO()
    csv.writer(si).writerow([h for h, _ in MIS_COLUMNS])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=MIS_History_Template.csv'})


@bp.route('/api/module/RP01/mis-history/summary')
@login_required
def mis_summary():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT COUNT(*) AS total_rows,
               COUNT(DISTINCT vcn_no) AS vessels,
               COALESCE(SUM(quantity), 0) AS quantity,
               COALESCE(SUM(COALESCE(cargo_amount,0) + COALESCE(infra_amount,0)
                          + COALESCE(toll_amount,0) + COALESCE(gangway_amount,0)
                          + COALESCE(mla_amount,0)), 0) AS amount,
               STRING_AGG(DISTINCT fin_year, ', ' ORDER BY fin_year) AS fin_years,
               MAX(uploaded_at)::text AS uploaded_at,
               MAX(uploaded_by) AS uploaded_by
        FROM mis_history
    ''')
    row = dict(cur.fetchone())
    conn.close()
    return jsonify(row)


@bp.route('/api/module/RP01/mis-history/data')
@login_required
def mis_data():
    page = int(request.args.get('page', 1))
    size = int(request.args.get('size', 25))
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('SELECT COUNT(*) FROM mis_history')
    total = cur.fetchone()['count']
    cur.execute('SELECT * FROM mis_history ORDER BY id LIMIT %s OFFSET %s',
                (size, (page - 1) * size))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'data': rows, 'last_page': max((total + size - 1) // size, 1), 'total': total})


@bp.route('/api/module/RP01/mis-history/upload', methods=['POST'])
@login_required
def mis_upload():
    perms = get_perms()
    if not (perms.get('can_add') and perms.get('can_delete')):
        return jsonify({'error': 'Upload replaces all data — add + delete permission required'}), 403
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file uploaded'}), 400
    rows, errors = parse_mis_csv(file.stream.read().decode('utf-8-sig'))
    if errors:
        return jsonify({'error': 'Fix these and re-upload (nothing was changed):',
                        'details': errors[:30], 'error_count': len(errors)}), 400
    if not rows:
        return jsonify({'error': 'No data rows found in file'}), 400

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM mis_history')
        deleted = cur.rowcount
        cols = DB_COLS + ['uploaded_by']
        sql = f'INSERT INTO mis_history ({", ".join(cols)}) VALUES ({", ".join(["%s"] * len(cols))})'
        user = session.get('email') or session.get('username')
        cur.executemany(sql, [[row[c] for c in DB_COLS] + [user] for row in rows])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify({'success': True, 'deleted': deleted, 'inserted': len(rows)})
